"""
Sherpa-ONNX 离线 TTS 服务。

使用 Sherpa-ONNX 的 VITS 中文模型进行离线语音合成，
无需网络连接，模型文件首次使用时自动下载并缓存到本地。

作为 Edge TTS 的离线替代方案。
"""

import os
import sys
import io
import wave
import struct
import threading
import time
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 全局 TTS 引擎实例（单例模式）
_tts_engine = None
_tts_engine_lock = threading.Lock()

# 模型缓存目录
_MODEL_CACHE_DIR = os.path.join(
    os.path.expanduser("~"), ".cache", "sherpa-onnx", "tts"
)

# ============================================================
# 可用的中文语音模型配置
# ============================================================
# Sherpa-ONNX 预训练的中文 VITS 模型
# 模型文件会自动从 huggingface 或 modelscope 下载

ZH_TTS_MODELS = {
    "vits-zh": {
        "name": "VITS 中文语音（默认）",
        "model_url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-zh-aishell3.tar.bz2",
        "model_dir": "vits-zh-aishell3",
        "model_file": "vits-aishell3.onnx",
        "tokens_file": "tokens.txt",
        "speakers": 2,  # 2 个说话人
        "sample_rate": 44100,
    },
    "vits-zh-llm": {
        "name": "VITS 中文语音（高质量）",
        "model_url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-zh-llm-aishell3.tar.bz2",
        "model_dir": "vits-zh-llm-aishell3",
        "model_file": "model.onnx",
        "tokens_file": "tokens.txt",
        "speakers": 2,
        "sample_rate": 44100,
    },
}

# 默认模型
_DEFAULT_MODEL = "vits-zh"

# 说话人名称映射
_SPEAKER_NAMES = {
    "vits-zh": {
        0: "女声（默认）",
        1: "男声",
    },
    "vits-zh-llm": {
        0: "女声（默认）",
        1: "男声",
    },
}


def _get_model_dir(model_key: str = _DEFAULT_MODEL) -> str:
    """获取模型目录路径。"""
    model_info = ZH_TTS_MODELS.get(model_key)
    if not model_info:
        raise ValueError(f"未知的模型: {model_key}")

    return os.path.join(_MODEL_CACHE_DIR, model_info["model_dir"])


def _ensure_model_downloaded(model_key: str = _DEFAULT_MODEL) -> str:
    """确保模型文件已下载，如果不存在则自动下载。

    Returns:
        str: 模型目录路径
    """
    model_info = ZH_TTS_MODELS.get(model_key)
    if not model_info:
        raise ValueError(f"未知的模型: {model_key}")

    model_dir = _get_model_dir(model_key)
    model_path = os.path.join(model_dir, model_info["model_file"])
    tokens_path = os.path.join(model_dir, model_info["tokens_file"])

    # 如果模型文件已存在，直接返回
    if os.path.isfile(model_path) and os.path.isfile(tokens_path):
        logger.info(f"Sherpa-ONNX 模型已存在: {model_dir}")
        return model_dir

    # 需要下载模型
    logger.info(f"正在下载 Sherpa-ONNX 中文 TTS 模型 ({model_key})...")
    logger.info(f"下载地址: {model_info['model_url']}")
    logger.info("首次下载可能需要几分钟，请耐心等待...")

    os.makedirs(model_dir, exist_ok=True)

    try:
        import urllib.request
        import tarfile

        # 下载模型压缩包
        archive_path = model_dir + ".tar.bz2"
        url = model_info["model_url"]

        def _report_progress(block_count, block_size, total_size):
            if total_size > 0:
                downloaded = block_count * block_size
                percent = min(100, int(downloaded * 100 / total_size))
                if percent % 10 == 0:
                    logger.info(f"  下载进度: {percent}%")

        urllib.request.urlretrieve(url, archive_path, _report_progress)

        # 解压
        logger.info("正在解压模型文件...")
        with tarfile.open(archive_path, "r:bz2") as tar:
            tar.extractall(path=_MODEL_CACHE_DIR)

        # 清理压缩包
        os.remove(archive_path)

        logger.info(f"模型下载完成: {model_dir}")
        return model_dir

    except Exception as e:
        logger.error(f"模型下载失败: {str(e)}")
        raise RuntimeError(f"Sherpa-ONNX 模型下载失败: {str(e)}")


def _get_tts_engine(model_key: str = _DEFAULT_MODEL):
    """获取或初始化 Sherpa-ONNX TTS 引擎（单例模式）。"""
    global _tts_engine

    if _tts_engine is not None:
        return _tts_engine

    with _tts_engine_lock:
        if _tts_engine is not None:
            return _tts_engine

        try:
            import sherpa_onnx

            # 确保模型已下载
            model_dir = _ensure_model_downloaded(model_key)
            model_info = ZH_TTS_MODELS[model_key]

            model_path = os.path.join(model_dir, model_info["model_file"])
            tokens_path = os.path.join(model_dir, model_info["tokens_file"])

            logger.info(f"正在加载 Sherpa-ONNX TTS 模型: {model_path}")

            # 配置 VITS 模型
            # vits-zh-aishell3 模型使用 lexicon 方式（非 character 方式），
            # 必须提供 lexicon 和 dict_dir 路径，否则会报错：
            # "Not a model using characters as modeling unit"
            lexicon_path = os.path.join(model_dir, "lexicon.txt")
            has_lexicon = os.path.isfile(lexicon_path)

            vits_config = sherpa_onnx.OfflineTtsVitsModelConfig(
                model=model_path,
                tokens=tokens_path,
                lexicon=lexicon_path if has_lexicon else "",
                dict_dir=model_dir if has_lexicon else "",
                data_dir="",
            )

            model_config = sherpa_onnx.OfflineTtsModelConfig(
                vits=vits_config,
                num_threads=2,
                debug=False,
                provider="cpu",
            )

            tts_config = sherpa_onnx.OfflineTtsConfig(
                model=model_config,
                max_num_sentences=1,
                silence_scale=0.2,
            )

            _tts_engine = sherpa_onnx.OfflineTts(tts_config)
            logger.info("Sherpa-ONNX TTS 模型加载完成")
            return _tts_engine

        except Exception as e:
            logger.error(f"Sherpa-ONNX TTS 引擎初始化失败: {str(e)}")
            raise RuntimeError(f"离线 TTS 引擎初始化失败: {str(e)}")


def get_available_models() -> dict:
    """获取可用的 TTS 模型列表。"""
    return {k: v["name"] for k, v in ZH_TTS_MODELS.items()}


def get_available_speakers(model_key: str = _DEFAULT_MODEL) -> dict:
    """获取指定模型的可用说话人列表。"""
    speakers = _SPEAKER_NAMES.get(model_key, {})
    return speakers


def text_to_speech(
    text: str,
    model_key: str = _DEFAULT_MODEL,
    speaker_id: int = 0,
    speed: float = 1.0,
) -> bytes:
    """文本转语音（离线，使用 Sherpa-ONNX）。

    Args:
        text: 要合成的文本
        model_key: 模型名称，默认 "vits-zh"
        speaker_id: 说话人 ID，默认 0（女声）
        speed: 语速，默认 1.0

    Returns:
        bytes: WAV 格式音频数据（16kHz, 16bit, mono）
    """
    if not text or not text.strip():
        return b""

    try:
        engine = _get_tts_engine(model_key)

        # 生成音频
        audio = engine.generate(text, sid=speaker_id, speed=speed)

        # 获取生成的音频数据
        samples = audio.samples
        sample_rate = audio.sample_rate

        if samples is None or len(samples) == 0:
            logger.warning("TTS 生成了空的音频数据")
            return b""

        # 将 float32 样本转换为 WAV 格式
        return _float32_to_wav(samples, sample_rate)

    except Exception as e:
        logger.error(f"Sherpa-ONNX TTS 合成失败: {str(e)}")
        raise RuntimeError(f"离线语音合成失败: {str(e)}")


def text_to_speech_stream(
    text: str,
    model_key: str = _DEFAULT_MODEL,
    speaker_id: int = 0,
    speed: float = 1.0,
    chunk_size_ms: int = 200,
):
    """文本转语音流式生成器（逐 chunk 返回 WAV 数据）。

    将完整音频按时间分片，实现边合成边播放的效果。

    Args:
        text: 要合成的文本
        model_key: 模型名称
        speaker_id: 说话人 ID
        speed: 语速
        chunk_size_ms: 每个 chunk 的时长（毫秒）

    Yields:
        bytes: WAV 格式音频数据块
    """
    try:
        audio_data = text_to_speech(text, model_key, speaker_id, speed)
        if not audio_data:
            return

        # 解析 WAV 头获取参数
        with wave.open(io.BytesIO(audio_data), "rb") as wf:
            sample_rate = wf.getframerate()
            sample_width = wf.getsampwidth()
            channels = wf.getnchannels()
            total_frames = wf.getnframes()

        # 计算每个 chunk 的帧数
        chunk_frames = int(sample_rate * chunk_size_ms / 1000)
        chunk_size = chunk_frames * sample_width * channels

        # 跳过 WAV 头（44 字节），逐块返回音频数据
        data_start = 44  # 标准 WAV 头长度
        offset = data_start

        while offset < len(audio_data):
            chunk = audio_data[offset:offset + chunk_size]
            if not chunk:
                break

            # 为每个 chunk 构建 WAV 头
            chunk_wav = _build_wav_header(
                num_samples=len(chunk) // (sample_width * channels),
                sample_rate=sample_rate,
                sample_width=sample_width,
                channels=channels,
            ) + chunk

            yield chunk_wav
            offset += chunk_size

    except Exception as e:
        logger.error(f"Sherpa-ONNX TTS 流式合成失败: {str(e)}")
        raise RuntimeError(f"离线语音流式合成失败: {str(e)}")


def _float32_to_wav(samples, sample_rate: int) -> bytes:
    """将 float32 样本数组转换为 WAV 格式字节数据。

    Args:
        samples: numpy float32 数组
        sample_rate: 采样率

    Returns:
        bytes: WAV 格式音频数据
    """
    import numpy as np

    # 确保是 float32 类型
    samples = np.asarray(samples, dtype=np.float32)

    # 限制范围 [-1.0, 1.0]
    samples = np.clip(samples, -1.0, 1.0)

    # 转换为 int16
    int_samples = (samples * 32767).astype(np.int16)

    # 写入 WAV
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)  # mono
        wf.setsampwidth(2)  # 16bit
        wf.setframerate(sample_rate)
        wf.writeframes(int_samples.tobytes())

    return buf.getvalue()


def _build_wav_header(
    num_samples: int,
    sample_rate: int,
    sample_width: int = 2,
    channels: int = 1,
) -> bytes:
    """构建 WAV 文件头。

    Args:
        num_samples: 音频样本数
        sample_rate: 采样率
        sample_width: 采样宽度（字节），默认 2（16bit）
        channels: 声道数，默认 1（mono）

    Returns:
        bytes: 44 字节的 WAV 头
    """
    data_size = num_samples * sample_width * channels
    file_size = 36 + data_size

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00" * data_size)  # dummy data

    header = buf.getvalue()[:44]
    return header


def is_available() -> bool:
    """检查 Sherpa-ONNX 是否可用。"""
    try:
        import sherpa_onnx
        return True
    except ImportError:
        return False


def is_model_downloaded(model_key: str = _DEFAULT_MODEL) -> bool:
    """检查模型是否已下载。"""
    model_info = ZH_TTS_MODELS.get(model_key)
    if not model_info:
        return False

    model_dir = _get_model_dir(model_key)
    model_path = os.path.join(model_dir, model_info["model_file"])
    tokens_path = os.path.join(model_dir, model_info["tokens_file"])

    return os.path.isfile(model_path) and os.path.isfile(tokens_path)
