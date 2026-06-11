"""
语音服务模块
- Edge TTS: 文本转语音（调用微软 Edge 浏览器 TTS 服务）
- FunASR: 语音识别（离线，基于阿里达摩院 FunASR）
- VAD: 语音活动检测（基于 FunASR 自带的 VAD 模型）
"""

import os
import asyncio
import html as _html
import tempfile
import uuid
import time
import struct
import wave
import io
import json
import base64
import aiohttp
from pathlib import Path
from flask import current_app


# ═══════════════════════════════════════════════════════════════
# Edge TTS — 文本转语音
# ═══════════════════════════════════════════════════════════════

# 可用的中文语音列表
ZH_VOICES = {
    "zh-CN-XiaoxiaoNeural": "晓晓（女，普通话）",
    "zh-CN-XiaoyiNeural": "晓伊（女，普通话）",
    "zh-CN-YunjianNeural": "云健（男，普通话）",
    "zh-CN-YunxiNeural": "云希（男，普通话）",
    "zh-CN-YunxiaNeural": "云夏（男，普通话）",
    "zh-CN-YunyangNeural": "云扬（男，普通话）",
    "zh-HK-HiuGaaiNeural": "晓佳（女，粤语）",
    "zh-TW-HsiaoChenNeural": "晓臻（女，台湾普通话）",
}

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

# 可用的说话风格（音色）
VOICE_STYLES = {
    "general": "普通",
    "affectionate": "亲切",
    "angry": "生气",
    "assistant": "助手",
    "calm": "平静",
    "chat": "聊天",
    "cheerful": "愉快",
    "customerservice": "客服",
    "depressed": "低落",
    "disgruntled": "不满",
    "embarrassed": "尴尬",
    "empathetic": "共情",
    "envy": "嫉妒",
    "excited": "兴奋",
    "fearful": "恐惧",
    "friendly": "友好",
    "gentle": "温柔",
    "hopeful": "希望",
    "lyrical": "抒情",
    "narration-professional": "旁白-专业",
    "narration-relaxed": "旁白-轻松",
    "newscast": "新闻",
    "newscast-casual": "新闻-休闲",
    "newscast-formal": "新闻-正式",
    "poetry-reading": "诗歌朗读",
    "sad": "悲伤",
    "serious": "严肃",
    "shouting": "喊叫",
    "sports-commentary": "体育解说",
    "sports-commentary-excited": "体育解说-激动",
    "whispering": "低语",
    "terrified": "恐惧",
}

DEFAULT_STYLE = "general"


def _xml_escape(text: str) -> str:
    """对文本进行 XML 转义，防止 SSML 解析出错。

    Edge TTS 的 SSML 中，文本内容不能包含 &, <, > 等 XML 特殊字符，
    否则会导致解析异常，合成出无关内容。
    """
    return _html.escape(text, quote=True)


def _build_ssml(text: str, voice: str, rate: str, pitch: str, style: str) -> str:
    """构建包含说话风格的 SSML 字符串。

    Args:
        text: 已 XML 转义的文本
        voice: 语音名称
        rate: 语速
        pitch: 语调
        style: 说话风格

    Returns:
        str: SSML 字符串
    """
    safe_text = _xml_escape(text)
    if style and style != DEFAULT_STYLE:
        return (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="zh-CN">'
            f'<voice name="{voice}">'
            f'<prosody rate="{rate}" pitch="{pitch}">'
            f'<mstts:express-as style="{style}">'
            f'{safe_text}'
            f'</mstts:express-as>'
            f'</prosody>'
            f'</voice>'
            f'</speak>'
        )
    else:
        return (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="zh-CN">'
            f'<voice name="{voice}">'
            f'<prosody rate="{rate}" pitch="{pitch}">'
            f'{safe_text}'
            f'</prosody>'
            f'</voice>'
            f'</speak>'
        )


async def _edge_tts_sync(text: str, voice: str = DEFAULT_VOICE, rate: str = "+0%", pitch: str = "+0Hz", style: str = DEFAULT_STYLE) -> bytes:
    """使用 edge-tts 合成语音，返回音频字节数据。

    注意：直接使用 edge-tts 库的 Communicate 类时，不能传入 SSML 字符串，
    因为 Communicate.__init__ 内部会对文本调用 escape() 转义 XML 特殊字符，
    导致 SSML 标签也被转义成普通文本被朗读。

    因此这里使用 edge-tts 库的底层 WebSocket 连接，自己构建完整的 SSML。
    """
    from edge_tts.communicate import (
        Communicate, TTSConfig, connect_id, date_to_string,
        ssml_headers_plus_data, WSS_URL, DRM, SEC_MS_GEC_VERSION,
        WSS_HEADERS, _SSL_CTX
    )

    ssml = _build_ssml(text, voice, rate, pitch, style)
    tts_config = TTSConfig(voice, rate, "+0%", pitch, "SentenceBoundary")

    audio_data = b""
    connect_id_val = connect_id()

    async with aiohttp.ClientSession(
        trust_env=True,
        timeout=aiohttp.ClientTimeout(total=None, connect=None, sock_connect=10, sock_read=60),
    ) as session, session.ws_connect(
        f"{WSS_URL}&ConnectionId={connect_id_val}"
        f"&Sec-MS-GEC={DRM.generate_sec_ms_gec()}"
        f"&Sec-MS-GEC-Version={SEC_MS_GEC_VERSION}",
        compress=15,
        proxy=None,
        headers=DRM.headers_with_muid(WSS_HEADERS),
        ssl=_SSL_CTX,
    ) as websocket:
        # 发送 speech.config 命令
        await websocket.send_str(
            f"X-Timestamp:{date_to_string()}\r\n"
            "Content-Type:application/json; charset=utf-8\r\n"
            "Path:speech.config\r\n\r\n"
            '{"context":{"synthesis":{"audio":{"metadataoptions":{'
            '"sentenceBoundaryEnabled":"false","wordBoundaryEnabled":"false"'
            "},"
            '"outputFormat":"audio-24khz-48kbitrate-mono-mp3"'
            "}}}}\r\n"
        )

        # 发送 SSML 请求
        ssml_request = ssml_headers_plus_data(connect_id_val, date_to_string(), ssml)
        await websocket.send_str(ssml_request)

        # 接收音频数据
        async for received in websocket:
            if received.type == aiohttp.WSMsgType.TEXT:
                encoded_data = received.data.encode("utf-8")
                # 检查是否是 turn.end
                if b"turn.end" in encoded_data:
                    break
            elif received.type == aiohttp.WSMsgType.BINARY:
                if len(received.data) < 2:
                    continue
                header_length = int.from_bytes(received.data[:2], "big")
                if header_length > len(received.data):
                    continue
                # 提取音频数据
                audio_chunk = received.data[2 + header_length:]
                if audio_chunk:
                    audio_data += audio_chunk
            elif received.type == aiohttp.WSMsgType.ERROR:
                break

    return audio_data


async def _edge_tts_stream(text: str, voice: str = DEFAULT_VOICE, rate: str = "+0%", pitch: str = "+0Hz", style: str = DEFAULT_STYLE):
    """Edge TTS 流式生成器，逐 chunk 返回音频数据。

    注意：直接使用 edge-tts 库的 Communicate 类时，不能传入 SSML 字符串，
    因为 Communicate.__init__ 内部会对文本调用 escape() 转义 XML 特殊字符，
    导致 SSML 标签也被转义成普通文本被朗读。

    因此这里使用 edge-tts 库的底层 WebSocket 连接，自己构建完整的 SSML。

    Yields:
        bytes: 每个音频 chunk 的二进制数据
    """
    from edge_tts.communicate import (
        Communicate, TTSConfig, connect_id, date_to_string,
        ssml_headers_plus_data, WSS_URL, DRM, SEC_MS_GEC_VERSION,
        WSS_HEADERS, _SSL_CTX
    )

    ssml = _build_ssml(text, voice, rate, pitch, style)
    tts_config = TTSConfig(voice, rate, "+0%", pitch, "SentenceBoundary")

    connect_id_val = connect_id()

    async with aiohttp.ClientSession(
        trust_env=True,
        timeout=aiohttp.ClientTimeout(total=None, connect=None, sock_connect=10, sock_read=60),
    ) as session, session.ws_connect(
        f"{WSS_URL}&ConnectionId={connect_id_val}"
        f"&Sec-MS-GEC={DRM.generate_sec_ms_gec()}"
        f"&Sec-MS-GEC-Version={SEC_MS_GEC_VERSION}",
        compress=15,
        proxy=None,
        headers=DRM.headers_with_muid(WSS_HEADERS),
        ssl=_SSL_CTX,
    ) as websocket:
        # 发送 speech.config 命令
        await websocket.send_str(
            f"X-Timestamp:{date_to_string()}\r\n"
            "Content-Type:application/json; charset=utf-8\r\n"
            "Path:speech.config\r\n\r\n"
            '{"context":{"synthesis":{"audio":{"metadataoptions":{'
            '"sentenceBoundaryEnabled":"false","wordBoundaryEnabled":"false"'
            "},"
            '"outputFormat":"audio-24khz-48kbitrate-mono-mp3"'
            "}}}}\r\n"
        )

        # 发送 SSML 请求
        ssml_request = ssml_headers_plus_data(connect_id_val, date_to_string(), ssml)
        await websocket.send_str(ssml_request)

        # 接收音频数据
        async for received in websocket:
            if received.type == aiohttp.WSMsgType.TEXT:
                encoded_data = received.data.encode("utf-8")
                if b"turn.end" in encoded_data:
                    break
            elif received.type == aiohttp.WSMsgType.BINARY:
                if len(received.data) < 2:
                    continue
                header_length = int.from_bytes(received.data[:2], "big")
                if header_length > len(received.data):
                    continue
                audio_chunk = received.data[2 + header_length:]
                if audio_chunk:
                    yield audio_chunk
            elif received.type == aiohttp.WSMsgType.ERROR:
                break


def text_to_speech_stream(text: str, voice: str = DEFAULT_VOICE, rate: str = "+0%", pitch: str = "+0Hz", style: str = DEFAULT_STYLE):
    """文本转语音流式生成器（同步包装器）。

    逐 chunk 从 Edge TTS 获取音频数据并 yield，实现边合成边输出。

    Args:
        text: 要合成的文本
        voice: 语音名称，默认 zh-CN-XiaoxiaoNeural
        rate: 语速，如 "+0%" 正常，"+50%" 加快，"-50%" 减慢
        pitch: 语调，如 "+0Hz" 正常，"+50Hz" 升高，"-50Hz" 降低
        style: 说话风格/音色，如 "general", "cheerful", "sad" 等

    Yields:
        bytes: 每个音频 chunk 的二进制数据
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        gen = _edge_tts_stream(text, voice, rate, pitch, style)
        while True:
            try:
                chunk = loop.run_until_complete(gen.__anext__())
                yield chunk
            except StopAsyncIteration:
                break
        loop.close()
    except Exception as e:
        raise RuntimeError(f"Edge TTS 流式合成失败: {str(e)}")


def text_to_speech(text: str, voice: str = DEFAULT_VOICE, rate: str = "+0%", pitch: str = "+0Hz", style: str = DEFAULT_STYLE) -> bytes:
    """文本转语音（同步包装器）。

    Args:
        text: 要合成的文本
        voice: 语音名称，默认 zh-CN-XiaoxiaoNeural
        rate: 语速，如 "+0%" 正常，"+50%" 加快，"-50%" 减慢
        pitch: 语调，如 "+0Hz" 正常，"+50Hz" 升高，"-50Hz" 降低
        style: 说话风格/音色，如 "general", "cheerful", "sad" 等

    Returns:
        bytes: 音频数据（MP3 格式）
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_data = loop.run_until_complete(_edge_tts_sync(text, voice, rate, pitch, style))
        loop.close()
        return audio_data
    except Exception as e:
        raise RuntimeError(f"Edge TTS 合成失败: {str(e)}")


def get_available_voices() -> dict:
    """获取可用的语音列表。"""
    return ZH_VOICES


def get_voice_styles() -> dict:
    """获取可用的说话风格列表。"""
    return VOICE_STYLES


# ═══════════════════════════════════════════════════════════════
# FunASR — 语音识别（离线）+ VAD 语音活动检测
# ═══════════════════════════════════════════════════════════════

# 全局 ASR 模型实例（延迟加载，只初始化一次）
_asr_model = None
_asr_model_lock = None


def _get_asr_model():
    """获取或初始化 FunASR 模型（单例模式）。"""
    global _asr_model, _asr_model_lock

    if _asr_model is not None:
        return _asr_model

    if _asr_model_lock is None:
        import threading
        _asr_model_lock = threading.Lock()

    with _asr_model_lock:
        if _asr_model is not None:
            return _asr_model

        try:
            from funasr import AutoModel

            # 使用 Paraformer 轻量模型（中文效果好，速度快）
            # 模型会在首次使用时自动下载
            model_dir = "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch"

            current_app.logger.info("正在加载 FunASR 模型（首次加载可能需要下载模型）...")

            _asr_model = AutoModel(
                model=model_dir,
                vad_model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
                punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
                disable_update=True,
                device="cpu",  # CPU 模式
            )

            current_app.logger.info("FunASR 模型加载完成")
            return _asr_model

        except Exception as e:
            current_app.logger.error(f"FunASR 模型加载失败: {str(e)}")
            raise RuntimeError(f"FunASR 模型加载失败: {str(e)}")


def _convert_to_wav(audio_data: bytes, source_format: str) -> bytes:
    """将音频数据转换为 WAV 格式（16kHz, 16bit, mono）。

    FunASR 对 WAV 格式支持最好，此函数确保输入格式正确。
    """
    # 如果已经是 wav，直接返回
    if source_format.endswith("wav"):
        return audio_data

    # 尝试使用 ffmpeg 转换（如果可用）
    try:
        import subprocess
        input_ext = source_format.split("/")[-1].split(";")[0]
        if not input_ext:
            input_ext = "webm"

        cmd = [
            "ffmpeg", "-y", "-i", "pipe:0",
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            "-f", "wav", "pipe:1"
        ]
        proc = subprocess.run(
            cmd, input=audio_data, capture_output=True, timeout=30
        )
        if proc.returncode == 0 and len(proc.stdout) > 44:
            return proc.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 如果没有 ffmpeg，返回原始数据（FunASR 内部可能也能处理）
    return audio_data


def speech_to_text(audio_data: bytes, audio_format: str = "webm") -> str:
    """语音识别：将音频数据转为文字。

    Args:
        audio_data: 音频二进制数据
        audio_format: 音频格式（webm, wav, mp3, ogg 等）

    Returns:
        str: 识别出的文字
    """
    # 转换为 WAV 格式
    wav_data = _convert_to_wav(audio_data, audio_format)

    # 保存到临时文件
    tmp_dir = current_app.config.get("TEMP_DIR", tempfile.gettempdir())
    tmp_path = os.path.join(tmp_dir, f"asr_{uuid.uuid4().hex}.wav")

    try:
        with open(tmp_path, "wb") as f:
            f.write(wav_data)

        model = _get_asr_model()
        result = model.generate(input=tmp_path)

        # 解析结果
        if isinstance(result, list) and len(result) > 0:
            text = result[0].get("text", "").strip()
            if text:
                return text

        if isinstance(result, dict) and "text" in result:
            return result["text"].strip()

        return ""

    except Exception as e:
        current_app.logger.error(f"FunASR 识别失败: {str(e)}")
        raise RuntimeError(f"语音识别失败: {str(e)}")

    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# VAD — 语音活动检测（服务端）
# ═══════════════════════════════════════════════════════════════

def vad_detect(audio_data: bytes, audio_format: str = "webm") -> dict:
    """使用 FunASR VAD 模型检测音频中的语音活动。

    返回检测结果，包含语音片段的起止时间（毫秒）。

    Args:
        audio_data: 音频二进制数据
        audio_format: 音频格式

    Returns:
        dict: {
            "has_speech": bool,       # 是否检测到语音
            "segments": [...],        # 语音片段列表
            "speech_duration_ms": int # 语音总时长（毫秒）
        }
    """
    wav_data = _convert_to_wav(audio_data, audio_format)

    tmp_dir = current_app.config.get("TEMP_DIR", tempfile.gettempdir())
    tmp_path = os.path.join(tmp_dir, f"vad_{uuid.uuid4().hex}.wav")

    try:
        with open(tmp_path, "wb") as f:
            f.write(wav_data)

        model = _get_asr_model()
        # 使用 VAD 模型检测
        result = model.generate(input=tmp_path, vad_only=True)

        segments = []
        total_duration = 0

        if isinstance(result, list):
            for seg in result:
                if isinstance(seg, dict):
                    start = seg.get("start", 0)
                    end = seg.get("end", 0)
                    if end > start:
                        segments.append({"start_ms": start, "end_ms": end})
                        total_duration += (end - start)

        return {
            "has_speech": len(segments) > 0,
            "segments": segments,
            "speech_duration_ms": total_duration,
        }

    except Exception as e:
        current_app.logger.error(f"VAD 检测失败: {str(e)}")
        return {"has_speech": False, "segments": [], "speech_duration_ms": 0}

    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# 音频格式工具
# ═══════════════════════════════════════════════════════════════

def get_audio_duration(audio_data: bytes, audio_format: str = "webm") -> float:
    """获取音频时长（秒）。"""
    try:
        import subprocess
        input_ext = audio_format.split("/")[-1].split(";")[0]
        if not input_ext:
            input_ext = "webm"

        cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
            "pipe:0"
        ]
        proc = subprocess.run(
            cmd, input=audio_data, capture_output=True, timeout=10
        )
        if proc.returncode == 0:
            duration = float(proc.stdout.strip())
            return duration
    except Exception:
        pass

    # 如果是 WAV 格式，手动计算
    if audio_format.endswith("wav") or audio_data[:4] == b"RIFF":
        try:
            with wave.open(io.BytesIO(audio_data), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return frames / rate
        except Exception:
            pass

    return 0.0
