"""
豆包（火山引擎）流式语音识别服务

基于火山引擎 SAUC（Speech Audio Understanding Cloud）协议：
- 文档：https://www.volcengine.com/docs/6561/1354869
- 参考：sauc_websocket_demo.py

功能：
1. 实时流式语音识别（WebSocket 双向流）
2. 支持 WAV/PCM 格式（自动使用 ffmpeg 转换）
3. 支持中间结果（实时字幕）和最终结果
4. 支持标点、数字格式化、ITN 等

配置（环境变量）：
- DOUBAO_ASR_APPID: 火山引擎 App Key（对应 demo 中的 app_key）
- DOUBAO_ASR_TOKEN: 火山引擎 Access Key（对应 demo 中的 access_key）
- DOUBAO_ASR_CLUSTER: 集群名称，默认 "volcengine_streaming_common"
"""
import os
import json
import time
import struct
import gzip
import uuid
import asyncio
import threading
import subprocess
from typing import Optional, Callable, List, Dict, Any, AsyncGenerator, Tuple
from flask import current_app
import aiohttp


# ── 日志 ──────────────────────────────────────────────────────────────────
import logging
logger = logging.getLogger(__name__)


# ── 常量 ──────────────────────────────────────────────────────────────────

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_SEGMENT_DURATION_MS = 200  # 每包音频时长（毫秒）
DEFAULT_WS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"

# 协议常量
class ProtocolVersion:
    V1 = 0b0001

class MessageType:
    CLIENT_FULL_REQUEST = 0b0001
    CLIENT_AUDIO_ONLY_REQUEST = 0b0010
    SERVER_FULL_RESPONSE = 0b1001
    SERVER_ERROR_RESPONSE = 0b1111

class MessageTypeSpecificFlags:
    NO_SEQUENCE = 0b0000
    POS_SEQUENCE = 0b0001
    NEG_SEQUENCE = 0b0010
    NEG_WITH_SEQUENCE = 0b0011

class SerializationType:
    NO_SERIALIZATION = 0b0000
    JSON = 0b0001

class CompressionType:
    GZIP = 0b0001


# ══════════════════════════════════════════════════════════════════════════
# 配置
# ══════════════════════════════════════════════════════════════════════════

def _get_config() -> dict:
    """获取豆包 ASR 配置（从环境变量读取）。

    .env 文件已由 load_dotenv 加载到 os.environ。
    """
    app_key = os.environ.get("DOUBAO_ASR_APPID") or current_app.config.get("DOUBAO_ASR_APPID", "")
    access_key = os.environ.get("DOUBAO_ASR_TOKEN") or current_app.config.get("DOUBAO_ASR_TOKEN", "")
    ws_url = os.environ.get("DOUBAO_ASR_WS_URL") or current_app.config.get("DOUBAO_ASR_WS_URL", DEFAULT_WS_URL)
    return {
        "app_key": app_key,
        "access_key": access_key,
        "ws_url": ws_url,
    }


def is_available() -> bool:
    """检查豆包 ASR 是否已配置可用。"""
    try:
        cfg = _get_config()
        return bool(cfg["app_key"] and cfg["access_key"])
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════════════════

class CommonUtils:
    @staticmethod
    def gzip_compress(data: bytes) -> bytes:
        return gzip.compress(data)

    @staticmethod
    def gzip_decompress(data: bytes) -> bytes:
        return gzip.decompress(data)

    @staticmethod
    def judge_wav(data: bytes) -> bool:
        if len(data) < 44:
            return False
        return data[:4] == b'RIFF' and data[8:12] == b'WAVE'

    @staticmethod
    def convert_to_wav(audio_data: bytes, source_format: str) -> bytes:
        """将音频数据转换为 WAV 格式（16kHz, 16bit, mono）。

        使用临时文件（带正确扩展名）确保 ffmpeg 能正确识别输入格式。

        Raises:
            RuntimeError: 如果 ffmpeg 不可用或转换失败
        """
        # 如果已经是 WAV，直接返回
        if CommonUtils.judge_wav(audio_data):
            return audio_data

        # 确定输入格式扩展名
        input_ext = source_format.split("/")[-1].split(";")[0]
        if not input_ext or input_ext == "webm":
            # webm 是浏览器录音的常见格式，ffmpeg 需要明确指定
            input_ext = "webm"

        # 使用临时文件确保 ffmpeg 能通过扩展名识别格式
        import tempfile
        import tempfile as _tempfile
        tmp_input_path = None
        tmp_output_path = None
        try:
            # 使用 mkstemp 代替 NamedTemporaryFile，避免 Windows 上的文件锁定问题
            fd1, tmp_input_path = _tempfile.mkstemp(suffix=f".{input_ext}")
            os.close(fd1)
            with open(tmp_input_path, "wb") as f:
                f.write(audio_data)

            fd2, tmp_output_path = _tempfile.mkstemp(suffix=".wav")
            os.close(fd2)

            cmd = [
                "ffmpeg", "-v", "quiet", "-y",
                "-i", tmp_input_path,
                "-acodec", "pcm_s16le",
                "-ac", "1",
                "-ar", str(DEFAULT_SAMPLE_RATE),
                "-f", "wav",
                tmp_output_path
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30)

            if result.returncode == 0:
                with open(tmp_output_path, "rb") as f:
                    wav_data = f.read()
                if len(wav_data) > 44 and CommonUtils.judge_wav(wav_data):
                    return wav_data

            # 转换失败，记录详细错误
            stderr_msg = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            logger.error(f"FFmpeg conversion failed (returncode={result.returncode}): {stderr_msg[:200]}")
            raise RuntimeError(
                f"音频转换失败: ffmpeg 返回码 {result.returncode}，"
                f"输入格式 {input_ext}，输出 WAV"
            )

        except FileNotFoundError:
            raise RuntimeError("ffmpeg 未安装，无法转换音频格式。请安装 ffmpeg 或使用 WAV 格式上传。")
        except subprocess.TimeoutExpired:
            raise RuntimeError("音频转换超时（30秒），文件可能过大。")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"音频转换异常: {str(e)}")
        finally:
            # 清理临时文件
            for tmp_path in (tmp_input_path, tmp_output_path):
                if tmp_path:
                    try:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                    except Exception:
                        pass

    @staticmethod
    def read_wav_info(data: bytes) -> Tuple[int, int, int, int, bytes]:
        """解析 WAV 文件头，返回 (num_channels, bytes_per_sample, sample_rate, num_frames, wave_data)。"""
        if len(data) < 44:
            raise ValueError("Invalid WAV file: too short")

        chunk_id = data[:4]
        if chunk_id != b'RIFF':
            raise ValueError("Invalid WAV file: not RIFF format")

        format_ = data[8:12]
        if format_ != b'WAVE':
            raise ValueError("Invalid WAV file: not WAVE format")

        audio_format = struct.unpack('<H', data[20:22])[0]
        num_channels = struct.unpack('<H', data[22:24])[0]
        sample_rate = struct.unpack('<I', data[24:28])[0]
        bits_per_sample = struct.unpack('<H', data[34:36])[0]

        # 查找 data 子块
        pos = 36
        while pos < len(data) - 8:
            subchunk_id = data[pos:pos+4]
            subchunk_size = struct.unpack('<I', data[pos+4:pos+8])[0]
            if subchunk_id == b'data':
                wave_data = data[pos+8:pos+8+subchunk_size]
                return (
                    num_channels,
                    bits_per_sample // 8,
                    sample_rate,
                    subchunk_size // (num_channels * (bits_per_sample // 8)),
                    wave_data
                )
            pos += 8 + subchunk_size

        raise ValueError("Invalid WAV file: no data subchunk found")


# ══════════════════════════════════════════════════════════════════════════
# 协议层
# ══════════════════════════════════════════════════════════════════════════

class AsrRequestHeader:
    """ASR 请求头（4 字节）。"""
    def __init__(self):
        self.message_type = MessageType.CLIENT_FULL_REQUEST
        self.message_type_specific_flags = MessageTypeSpecificFlags.POS_SEQUENCE
        self.serialization_type = SerializationType.JSON
        self.compression_type = CompressionType.GZIP
        self.reserved_data = bytes([0x00])

    def with_message_type(self, message_type: int) -> 'AsrRequestHeader':
        self.message_type = message_type
        return self

    def with_message_type_specific_flags(self, flags: int) -> 'AsrRequestHeader':
        self.message_type_specific_flags = flags
        return self

    def with_serialization_type(self, serialization_type: int) -> 'AsrRequestHeader':
        self.serialization_type = serialization_type
        return self

    def with_compression_type(self, compression_type: int) -> 'AsrRequestHeader':
        self.compression_type = compression_type
        return self

    def with_reserved_data(self, reserved_data: bytes) -> 'AsrRequestHeader':
        self.reserved_data = reserved_data
        return self

    def to_bytes(self) -> bytes:
        header = bytearray()
        header.append((ProtocolVersion.V1 << 4) | 1)
        header.append((self.message_type << 4) | self.message_type_specific_flags)
        header.append((self.serialization_type << 4) | self.compression_type)
        header.extend(self.reserved_data)
        return bytes(header)

    @staticmethod
    def default_header() -> 'AsrRequestHeader':
        return AsrRequestHeader()


class RequestBuilder:
    """构建 ASR 请求数据包。"""

    @staticmethod
    def new_auth_headers(cfg: dict) -> Dict[str, str]:
        reqid = str(uuid.uuid4())
        return {
            "X-Api-Resource-Id": "volc.bigasr.sauc.duration",
            "X-Api-Request-Id": reqid,
            "X-Api-Access-Key": cfg["access_key"],
            "X-Api-App-Key": cfg["app_key"]
        }

    @staticmethod
    def new_full_client_request(seq: int) -> bytes:
        """构建完整的客户端请求（包含音频参数配置）。"""
        header = AsrRequestHeader.default_header() \
            .with_message_type_specific_flags(MessageTypeSpecificFlags.POS_SEQUENCE)

        payload = {
            "user": {
                "uid": "demo_uid"
            },
            "audio": {
                "format": "wav",
                "codec": "raw",
                "rate": DEFAULT_SAMPLE_RATE,
                "bits": 16,
                "channel": 1
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": True,
                "show_utterances": True,
                "enable_nonstream": False
            }
        }

        payload_bytes = json.dumps(payload).encode('utf-8')
        compressed_payload = CommonUtils.gzip_compress(payload_bytes)
        payload_size = len(compressed_payload)

        request = bytearray()
        request.extend(header.to_bytes())
        request.extend(struct.pack('>i', seq))
        request.extend(struct.pack('>I', payload_size))
        request.extend(compressed_payload)

        return bytes(request)

    @staticmethod
    def new_audio_only_request(seq: int, segment: bytes, is_last: bool = False) -> bytes:
        """构建纯音频数据请求。"""
        header = AsrRequestHeader.default_header()
        if is_last:
            header.with_message_type_specific_flags(MessageTypeSpecificFlags.NEG_WITH_SEQUENCE)
            seq = -seq
        else:
            header.with_message_type_specific_flags(MessageTypeSpecificFlags.POS_SEQUENCE)
        header.with_message_type(MessageType.CLIENT_AUDIO_ONLY_REQUEST)

        request = bytearray()
        request.extend(header.to_bytes())
        request.extend(struct.pack('>i', seq))

        compressed_segment = CommonUtils.gzip_compress(segment)
        request.extend(struct.pack('>I', len(compressed_segment)))
        request.extend(compressed_segment)

        return bytes(request)


class AsrResponse:
    """ASR 响应。"""
    def __init__(self):
        self.code = 0
        self.event = 0
        self.is_last_package = False
        self.payload_sequence = 0
        self.payload_size = 0
        self.payload_msg = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "event": self.event,
            "is_last_package": self.is_last_package,
            "payload_sequence": self.payload_sequence,
            "payload_size": self.payload_size,
            "payload_msg": self.payload_msg
        }

    def get_text(self) -> str:
        """从响应中提取识别文本。

        豆包 SAUC 协议响应结构：
        {
            "text": "中间/最终识别文本",
            "utterances": [
                {
                    "text": "语句文本",
                    "definite": true/false,  # true=最终结果, false=中间结果
                    "start_time": 501,
                    "end_time": 1922,
                    "words": [...]
                }
            ],
            "additions": {"log_id": "..."}
        }
        """
        if not self.payload_msg:
            return ""

        if isinstance(self.payload_msg, str):
            return self.payload_msg

        if not isinstance(self.payload_msg, dict):
            return ""

        # 1. 优先从 utterances 中提取文本（豆包 SAUC 协议）
        utterances = self.payload_msg.get("utterances")
        if utterances and isinstance(utterances, list) and len(utterances) > 0:
            texts = []
            for utt in utterances:
                if isinstance(utt, dict) and utt.get("text"):
                    texts.append(utt["text"])
            if texts:
                return "".join(texts)

        # 2. 其次从顶层 text 字段提取
        text = self.payload_msg.get("text", "")
        if text:
            return str(text)

        # 3. 尝试 result 字段（豆包 SAUC 协议中，text/utterances 可能在 result 子对象中）
        result = self.payload_msg.get("result")
        if result and isinstance(result, dict):
            # 3a. 从 result 中提取 utterances
            result_utterances = result.get("utterances")
            if result_utterances and isinstance(result_utterances, list) and len(result_utterances) > 0:
                texts = []
                for utt in result_utterances:
                    if isinstance(utt, dict) and utt.get("text"):
                        texts.append(utt["text"])
                if texts:
                    return "".join(texts)
            # 3b. 从 result 中提取 text
            result_text = result.get("text", "")
            if result_text:
                return str(result_text)
            # 3c. 从 result 中提取 result（嵌套）
            inner_result = result.get("result")
            if inner_result and isinstance(inner_result, str):
                return inner_result

        return ""

    def is_final(self) -> bool:
        """是否为最终结果。"""
        return self.is_last_package or self.code != 0


class ResponseParser:
    """解析 ASR 响应数据包。"""

    @staticmethod
    def parse_response(msg: bytes) -> AsrResponse:
        response = AsrResponse()

        header_size = msg[0] & 0x0f
        message_type = msg[1] >> 4
        message_type_specific_flags = msg[1] & 0x0f
        serialization_method = msg[2] >> 4
        message_compression = msg[2] & 0x0f

        payload = msg[header_size*4:]

        # 解析 message_type_specific_flags
        if message_type_specific_flags & 0x01:
            response.payload_sequence = struct.unpack('>i', payload[:4])[0]
            payload = payload[4:]
        if message_type_specific_flags & 0x02:
            response.is_last_package = True
        if message_type_specific_flags & 0x04:
            response.event = struct.unpack('>i', payload[:4])[0]
            payload = payload[4:]

        # 解析 message_type
        if message_type == MessageType.SERVER_FULL_RESPONSE:
            response.payload_size = struct.unpack('>I', payload[:4])[0]
            payload = payload[4:]
        elif message_type == MessageType.SERVER_ERROR_RESPONSE:
            response.code = struct.unpack('>i', payload[:4])[0]
            response.payload_size = struct.unpack('>I', payload[4:8])[0]
            payload = payload[8:]

        if not payload:
            return response

        # 解压缩
        if message_compression == CompressionType.GZIP:
            try:
                payload = CommonUtils.gzip_decompress(payload)
            except Exception as e:
                logger.error(f"Failed to decompress payload: {e}")
                return response

        # 解析 payload
        try:
            if serialization_method == SerializationType.JSON:
                response.payload_msg = json.loads(payload.decode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to parse payload: {e}")

        return response


# ══════════════════════════════════════════════════════════════════════════
# WebSocket 客户端
# ══════════════════════════════════════════════════════════════════════════

class AsrWsClient:
    """ASR WebSocket 客户端，基于 SAUC 协议。"""

    def __init__(self, url: str, segment_duration: int = DEFAULT_SEGMENT_DURATION_MS):
        self.seq = 1
        self.url = url
        self.segment_duration = segment_duration
        self.conn = None
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.conn and not self.conn.closed:
            await self.conn.close()
        if self.session and not self.session.closed:
            await self.session.close()

    def get_segment_size(self, content: bytes) -> int:
        """根据 WAV 信息计算每段音频大小。"""
        try:
            channel_num, samp_width, frame_rate, _, _ = CommonUtils.read_wav_info(content)[:5]
            size_per_sec = channel_num * samp_width * frame_rate
            segment_size = size_per_sec * self.segment_duration // 1000
            return segment_size
        except Exception as e:
            logger.error(f"Failed to calculate segment size: {e}")
            raise

    async def create_connection(self) -> None:
        """创建 WebSocket 连接。"""
        cfg = _get_config()
        headers = RequestBuilder.new_auth_headers(cfg)
        try:
            self.conn = await self.session.ws_connect(
                self.url,
                headers=headers
            )
            logger.info(f"Connected to {self.url}")
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            raise

    async def send_full_client_request(self) -> None:
        """发送完整客户端请求（包含音频参数配置）。"""
        request = RequestBuilder.new_full_client_request(self.seq)
        self.seq += 1
        try:
            await self.conn.send_bytes(request)
            logger.info(f"Sent full client request with seq: {self.seq - 1}")

            msg = await self.conn.receive()
            if msg.type == aiohttp.WSMsgType.BINARY:
                response = ResponseParser.parse_response(msg.data)
                logger.info(f"Received response: {response.to_dict()}")
            else:
                logger.error(f"Unexpected message type: {msg.type}")
        except Exception as e:
            logger.error(f"Failed to send full client request: {e}")
            raise

    async def send_messages(self, segment_size: int, content: bytes) -> AsyncGenerator[None, None]:
        """发送音频数据段。"""
        audio_segments = self.split_audio(content, segment_size)
        total_segments = len(audio_segments)

        for i, segment in enumerate(audio_segments):
            is_last = (i == total_segments - 1)
            request = RequestBuilder.new_audio_only_request(
                self.seq,
                segment,
                is_last=is_last
            )
            await self.conn.send_bytes(request)
            logger.info(f"Sent audio segment with seq: {self.seq} (last: {is_last})")

            if not is_last:
                self.seq += 1

            await asyncio.sleep(self.segment_duration / 1000)
            yield

    async def recv_messages(self) -> AsyncGenerator[AsrResponse, None]:
        """接收识别结果。"""
        try:
            async for msg in self.conn:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    response = ResponseParser.parse_response(msg.data)
                    yield response

                    if response.is_last_package or response.code != 0:
                        break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {msg.data}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.info("WebSocket connection closed")
                    break
        except Exception as e:
            logger.error(f"Error receiving messages: {e}")
            raise

    async def start_audio_stream(self, segment_size: int, content: bytes) -> AsyncGenerator[AsrResponse, None]:
        """启动音频流处理，同时发送和接收。"""
        async def sender():
            async for _ in self.send_messages(segment_size, content):
                pass

        sender_task = asyncio.create_task(sender())

        try:
            async for response in self.recv_messages():
                yield response
        finally:
            sender_task.cancel()
            try:
                await sender_task
            except asyncio.CancelledError:
                pass

    @staticmethod
    def split_audio(data: bytes, segment_size: int) -> List[bytes]:
        """将音频数据分割成固定大小的段。"""
        if segment_size <= 0:
            return []

        segments = []
        for i in range(0, len(data), segment_size):
            end = i + segment_size
            if end > len(data):
                end = len(data)
            segments.append(data[i:end])
        return segments

    async def execute(self, audio_data: bytes, audio_format: str = "webm") -> AsyncGenerator[AsrResponse, None]:
        """执行语音识别。

        Args:
            audio_data: 音频二进制数据
            audio_format: 音频格式（webm, wav, mp3, ogg 等）

        Yields:
            AsrResponse: 识别结果
        """
        if not audio_data:
            raise ValueError("Audio data is empty")

        if not self.url:
            raise ValueError("URL is empty")

        self.seq = 1

        try:
            # 1. 转换为 WAV 格式
            wav_data = CommonUtils.convert_to_wav(audio_data, audio_format)

            # 2. 计算分段大小
            segment_size = self.get_segment_size(wav_data)

            # 3. 创建 WebSocket 连接
            await self.create_connection()

            # 4. 发送完整客户端请求
            await self.send_full_client_request()

            # 5. 启动音频流处理
            async for response in self.start_audio_stream(segment_size, wav_data):
                yield response

        except Exception as e:
            logger.error(f"Error in ASR execution: {e}")
            raise
        finally:
            if self.conn:
                await self.conn.close()


# ══════════════════════════════════════════════════════════════════════════
# 同步接口（供现有代码调用）
# ══════════════════════════════════════════════════════════════════════════

def speech_to_text(audio_data: bytes, audio_format: str = "webm") -> str:
    """语音识别：将音频数据转为文字（同步接口）。

    使用豆包 ASR（SAUC 协议）进行语音识别。
    此函数会阻塞直到识别完成，适合非实时场景。
    只返回最终结果（definite=True 的 utterance 文本），不包含中间结果。

    Args:
        audio_data: 音频二进制数据
        audio_format: 音频格式（webm, wav, mp3, ogg 等）

    Returns:
        str: 识别出的文字
    """
    if not is_available():
        raise RuntimeError("豆包 ASR 未配置，请设置 DOUBAO_ASR_APPID 和 DOUBAO_ASR_TOKEN")

    cfg = _get_config()
    final_texts = []
    error_msg = None

    async def _run():
        nonlocal error_msg
        try:
            async with AsrWsClient(cfg["ws_url"]) as client:
                async for response in client.execute(audio_data, audio_format):
                    # 只收集最终结果（is_last_package 或 definite=True 的 utterance）
                    if response.is_final():
                        text = response.get_text()
                        if text:
                            final_texts.append(text)
                        break
                    # 也收集 definite=True 的 utterance（语句结束）
                    if response.payload_msg and isinstance(response.payload_msg, dict):
                        utterances = response.payload_msg.get("utterances", [])
                        if utterances and isinstance(utterances, list):
                            for utt in utterances:
                                if isinstance(utt, dict) and utt.get("definite") and utt.get("text"):
                                    final_texts.append(utt["text"])
        except Exception as e:
            error_msg = str(e)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()

    if error_msg:
        raise RuntimeError(f"豆包 ASR 识别失败: {error_msg}")

    result = "".join(final_texts)
    logger.info(f"speech_to_text 返回: type={type(result).__name__}, len={len(result)}, text={result[:200]!r}")
    return result


def stream_recognize(
    audio_generator,
    audio_format: str = "wav",
    on_result: Optional[Callable] = None,
    on_error: Optional[Callable] = None,
    on_final: Optional[Callable] = None,
):
    """流式语音识别（同步包装器）。

    用于实时字幕场景，逐 chunk 发送音频并接收识别结果。

    Args:
        audio_generator: 生成器/迭代器，yield 音频字节数据
        audio_format: 音频格式（wav, pcm 等）
        on_result: 每帧识别结果回调（含中间结果）
        on_error: 错误回调
        on_final: 最终结果回调
    """
    if not is_available():
        error_msg = "豆包 ASR 未配置，请设置 DOUBAO_ASR_APPID 和 DOUBAO_ASR_TOKEN"
        if on_error:
            on_error(error_msg)
        return

    cfg = _get_config()

    async def _run():
        # 收集所有音频数据
        all_data = b""
        for chunk in audio_generator:
            all_data += chunk

        if not all_data:
            return

        try:
            async with AsrWsClient(cfg["ws_url"]) as client:
                async for response in client.execute(all_data, audio_format):
                    text = response.get_text()
                    if text:
                        if response.is_final():
                            if on_final:
                                on_final(text)
                        else:
                            if on_result:
                                on_result(text)
                    if response.is_final():
                        break
        except Exception as e:
            if on_error:
                on_error(str(e))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()


def get_audio_duration(audio_data: bytes, audio_format: str = "webm") -> float:
    """获取音频时长（秒）。"""
    try:
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
    return 0.0
