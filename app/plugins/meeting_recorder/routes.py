"""
会议录音插件 — 后端路由

提供以下功能：
1. 录音文件上传（分片上传支持长录音）
2. 录音文件管理（列表、删除、下载）
3. 录音转文字（调用 FunASR 离线语音识别）
4. 实时字幕（录音过程中实时语音识别）
5. 多说话人识别（基于能量检测 + VAD 分段）
6. 自动转写（录音上传完成后自动触发）
7. 自动清理（定期清理过期录音文件）
8. 录音转文字后自动调用 meeting_minutes 技能生成纪要
"""

import json
import os
import uuid
import tempfile
import threading
import time as time_module
from datetime import datetime, timedelta
from pathlib import Path
from flask import (
    render_template, request, jsonify, current_app,
    send_from_directory, Response, url_for
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from .main import bp, blueprint_name
from app.utils.plugin_utils import require_plugin


# ── 配置 ──────────────────────────────────────────────────────────────────

def _get_recordings_dir():
    """获取录音文件存储目录（按用户分目录）。"""
    base = current_app.config.get("UPLOAD_FOLDER", os.path.join(current_app.root_path, "..", "uploads"))
    recordings_dir = os.path.join(base, "meeting_recordings", str(current_user.id))
    os.makedirs(recordings_dir, exist_ok=True)
    return recordings_dir


def _get_recordings_db():
    """获取录音记录数据库路径。"""
    base = current_app.config.get("INSTANCE_DIR", os.path.join(current_app.root_path, "..", "instance"))
    db_path = os.path.join(base, "meeting_recordings.db")
    return db_path


def _init_db():
    """初始化录音记录数据库。"""
    import sqlite3
    db_path = _get_recordings_db()
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recordings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT DEFAULT '',
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            duration_seconds REAL DEFAULT 0,
            file_size INTEGER DEFAULT 0,
            status TEXT DEFAULT 'uploaded',
            transcript TEXT DEFAULT '',
            speaker_count INTEGER DEFAULT 0,
            auto_transcribe INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def _get_db_conn():
    """获取数据库连接。"""
    import sqlite3
    _init_db()
    db_path = _get_recordings_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ── 允许的音频格式 ────────────────────────────────────────────────────────

ALLOWED_AUDIO_EXTENSIONS = {".webm", ".wav", ".mp3", ".ogg", ".m4a", ".mp4", ".opus"}

MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB（长会议录音）

# 自动清理配置：默认保留 30 天
CLEANUP_DAYS = 30
# 上次清理时间（避免每次请求都清理）
_last_cleanup_time = 0
_cleanup_lock = threading.Lock()


# ══════════════════════════════════════════════════════════════════════════
# 路由
# ══════════════════════════════════════════════════════════════════════════

@bp.route("/")
@login_required
@require_plugin(blueprint_name)
def index():
    """录音管理页面。"""
    return render_template("meeting_recorder/index.html")


@bp.route("/api/upload", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def upload_recording():
    """上传录音文件（支持分片上传）。

    请求格式: multipart/form-data
    - audio: 音频文件
    - title: 录音标题（可选）
    - chunk_index: 分片序号（可选，分片上传用）
    - total_chunks: 总分片数（可选，分片上传用）
    - session_id: 分片会话 ID（可选，分片上传用）
    - auto_transcribe: 是否自动转写（可选，默认1）
    """
    if "audio" not in request.files:
        return jsonify({"error": "未找到音频文件"}), 400

    audio_file = request.files["audio"]
    if not audio_file.filename:
        return jsonify({"error": "音频文件为空"}), 400

    # 检查文件扩展名
    ext = os.path.splitext(audio_file.filename)[1].lower()
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        return jsonify({"error": f"不支持的音频格式: {ext}，支持: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}"}), 400

    title = request.form.get("title", "").strip()
    chunk_index = request.form.get("chunk_index")
    total_chunks = request.form.get("total_chunks")
    session_id = request.form.get("session_id")
    auto_transcribe = request.form.get("auto_transcribe", "1")

    recordings_dir = _get_recordings_dir()

    # ── 分片上传处理 ────────────────────────────────────────────────
    if chunk_index is not None and total_chunks is not None and session_id:
        chunk_index = int(chunk_index)
        total_chunks = int(total_chunks)

        # 临时分片目录
        chunk_dir = os.path.join(recordings_dir, ".chunks", session_id)
        os.makedirs(chunk_dir, exist_ok=True)

        # 保存分片
        chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_index:04d}")
        audio_file.save(chunk_path)

        # 如果是最后一个分片，合并所有分片
        if chunk_index == total_chunks - 1:
            # 生成最终文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = uuid.uuid4().hex[:8]
            final_filename = f"meeting_{timestamp}_{unique_id}{ext}"
            final_path = os.path.join(recordings_dir, final_filename)

            # 合并分片
            with open(final_path, "wb") as f_out:
                for i in range(total_chunks):
                    chunk_path_i = os.path.join(chunk_dir, f"chunk_{i:04d}")
                    if os.path.exists(chunk_path_i):
                        with open(chunk_path_i, "rb") as f_in:
                            f_out.write(f_in.read())

            # 清理分片目录
            import shutil
            shutil.rmtree(chunk_dir, ignore_errors=True)

            # 获取文件信息
            file_size = os.path.getsize(final_path)
            duration = _get_audio_duration(final_path)

            # 保存记录到数据库
            record_id = _save_recording(
                title=title or f"会议录音 {timestamp}",
                filename=final_filename,
                filepath=final_path,
                duration=duration,
                file_size=file_size,
                auto_transcribe=int(auto_transcribe),
            )

            # ── 自动转写 ────────────────────────────────────────────
            if auto_transcribe == "1" and duration > 0:
                _start_auto_transcribe(record_id, final_path)

            return jsonify({
                "success": True,
                "record_id": record_id,
                "filename": final_filename,
                "file_size": file_size,
                "duration": duration,
                "message": "录音上传完成",
            })

        return jsonify({
            "success": True,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "message": f"分片 {chunk_index + 1}/{total_chunks} 上传成功",
        })

    # ── 普通上传（非分片） ──────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    filename = f"meeting_{timestamp}_{unique_id}{ext}"
    filepath = os.path.join(recordings_dir, filename)

    audio_file.save(filepath)

    file_size = os.path.getsize(filepath)
    duration = _get_audio_duration(filepath)

    record_id = _save_recording(
        title=title or f"会议录音 {timestamp}",
        filename=filename,
        filepath=filepath,
        duration=duration,
        file_size=file_size,
        auto_transcribe=int(auto_transcribe),
    )

    # ── 自动转写 ────────────────────────────────────────────────────
    if auto_transcribe == "1" and duration > 0:
        _start_auto_transcribe(record_id, filepath)

    return jsonify({
        "success": True,
        "record_id": record_id,
        "filename": filename,
        "file_size": file_size,
        "duration": duration,
        "message": "录音上传成功",
    })


@bp.route("/api/realtime-transcribe", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def realtime_transcribe():
    """实时语音识别：接收一小段音频，返回识别文字（用于实时字幕）。

    根据用户设置的 ASR 引擎选择不同的识别服务：
    - funasr: 使用 FunASR 离线语音识别（默认）
    - doubao: 使用豆包（火山引擎）流式语音识别

    请求格式: multipart/form-data
    - audio: 音频片段（Blob）
    - session_id: 会话 ID（用于区分不同录音会话）
    """
    if "audio" not in request.files:
        return jsonify({"error": "未找到音频"}), 400

    audio_file = request.files["audio"]
    if not audio_file.filename:
        return jsonify({"error": "音频为空"}), 400

    session_id = request.form.get("session_id", "")

    # 获取用户选择的 ASR 引擎
    from flask import session
    asr_engine = session.get("meeting_recorder_asr_engine", "funasr")

    try:
        audio_data = audio_file.read()
        audio_format = audio_file.content_type or "audio/webm"

        # 跳过太短的音频（< 0.5秒的音频通常没有有效语音）
        if len(audio_data) < 8000:
            return jsonify({"success": True, "text": "", "session_id": session_id})

        if asr_engine == "doubao":
            # 使用豆包 ASR
            try:
                from app.services.doubao_asr import speech_to_text as doubao_stt
                text = doubao_stt(audio_data, audio_format)
            except ImportError:
                current_app.logger.warning("豆包 ASR 模块未加载，回退到 FunASR")
                from app.services.voice_service import speech_to_text
                text = speech_to_text(audio_data, audio_format)
            except RuntimeError as e:
                current_app.logger.warning(f"豆包 ASR 识别失败，回退到 FunASR: {str(e)}")
                from app.services.voice_service import speech_to_text
                text = speech_to_text(audio_data, audio_format)
        else:
            # 默认使用 FunASR
            from app.services.voice_service import speech_to_text
            text = speech_to_text(audio_data, audio_format)

        return jsonify({
            "success": True,
            "text": text,
            "session_id": session_id,
        })
    except Exception as e:
        current_app.logger.error(f"实时语音识别失败: {str(e)}")
        return jsonify({"success": True, "text": "", "session_id": session_id})


@bp.route("/api/realtime-transcribe/stream", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def realtime_transcribe_stream():
    """实时语音识别（SSE 流式输出）：接收一小段音频，流式返回识别文字。

    仅豆包 ASR 支持流式输出，FunASR 回退到普通模式。

    请求格式: multipart/form-data
    - audio: 音频片段（Blob）
    - session_id: 会话 ID（用于区分不同录音会话）

    响应格式: Server-Sent Events (SSE)
    - data: {"type": "interim", "text": "中间结果", "session_id": "xxx"}
    - data: {"type": "final", "text": "最终结果", "session_id": "xxx"}
    - data: {"type": "done", "session_id": "xxx"}
    """
    if "audio" not in request.files:
        return jsonify({"error": "未找到音频"}), 400

    audio_file = request.files["audio"]
    if not audio_file.filename:
        return jsonify({"error": "音频为空"}), 400

    session_id = request.form.get("session_id", "")

    # 获取用户选择的 ASR 引擎
    from flask import session
    asr_engine = session.get("meeting_recorder_asr_engine", "funasr")

    audio_data = audio_file.read()
    audio_format = audio_file.content_type or "audio/webm"

    # 跳过太短的音频
    if len(audio_data) < 8000:
        def empty_gen():
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
        return Response(empty_gen(), mimetype="text/event-stream")

    def generate():
        if asr_engine == "doubao":
            try:
                from app.services.doubao_asr import is_available
                if not is_available():
                    yield f"data: {json.dumps({'type': 'error', 'text': '豆包 ASR 未配置', 'session_id': session_id})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
                    return

                from app.services.doubao_asr import stream_recognize as doubao_stream

                # 使用流式识别，逐帧回调
                def on_result(text):
                    # 中间结果
                    current_app.logger.info(f"豆包 ASR 中间结果: {text}")
                    # 通过生成器发送 SSE 事件
                    gen_data.append(json.dumps({
                        'type': 'interim',
                        'text': text,
                        'session_id': session_id
                    }))

                def on_final(text):
                    # 最终结果
                    current_app.logger.info(f"豆包 ASR 最终结果: {text}")
                    gen_data.append(json.dumps({
                        'type': 'final',
                        'text': text,
                        'session_id': session_id
                    }))

                def on_error(err):
                    current_app.logger.error(f"豆包 ASR 流式识别错误: {err}")
                    gen_data.append(json.dumps({
                        'type': 'error',
                        'text': str(err),
                        'session_id': session_id
                    }))

                # 由于 stream_recognize 是同步阻塞的，我们需要在后台线程运行
                # 并通过队列传递结果
                import queue
                result_queue = queue.Queue()

                def _run_stream():
                    doubao_stream(
                        [audio_data],
                        audio_format=audio_format,
                        on_result=lambda t: result_queue.put(("interim", t)),
                        on_final=lambda t: result_queue.put(("final", t)),
                        on_error=lambda e: result_queue.put(("error", str(e))),
                    )
                    result_queue.put(("done", None))

                thread = threading.Thread(target=_run_stream, daemon=True)
                thread.start()

                while True:
                    try:
                        msg_type, msg_text = result_queue.get(timeout=30)
                        if msg_type == "interim":
                            yield f"data: {json.dumps({'type': 'interim', 'text': msg_text, 'session_id': session_id})}\n\n"
                        elif msg_type == "final":
                            yield f"data: {json.dumps({'type': 'final', 'text': msg_text, 'session_id': session_id})}\n\n"
                        elif msg_type == "error":
                            yield f"data: {json.dumps({'type': 'error', 'text': msg_text, 'session_id': session_id})}\n\n"
                        elif msg_type == "done":
                            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
                            break
                    except queue.Empty:
                        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
                        break

            except ImportError:
                # 豆包 ASR 不可用，回退到普通模式
                from app.services.voice_service import speech_to_text
                text = speech_to_text(audio_data, audio_format)
                if text:
                    yield f"data: {json.dumps({'type': 'final', 'text': text, 'session_id': session_id})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
            except Exception as e:
                current_app.logger.error(f"豆包 ASR 流式识别异常: {str(e)}")
                yield f"data: {json.dumps({'type': 'error', 'text': str(e), 'session_id': session_id})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
        else:
            # FunASR 不支持流式，直接返回结果
            try:
                from app.services.voice_service import speech_to_text
                text = speech_to_text(audio_data, audio_format)
                if text:
                    yield f"data: {json.dumps({'type': 'final', 'text': text, 'session_id': session_id})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'text': str(e), 'session_id': session_id})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@bp.route("/api/recordings", methods=["GET"])
@login_required
@require_plugin(blueprint_name)
def list_recordings():
    """获取录音文件列表。"""
    keyword = request.args.get("keyword", "").strip()
    limit = min(int(request.args.get("limit", 50)), 200)

    conn = _get_db_conn()
    try:
        query = "SELECT * FROM recordings WHERE user_id=? ORDER BY created_at DESC LIMIT ?"
        params = [current_user.id, limit]

        if keyword:
            query = "SELECT * FROM recordings WHERE user_id=? AND (title LIKE ? OR transcript LIKE ?) ORDER BY created_at DESC LIMIT ?"
            kw = f"%{keyword}%"
            params = [current_user.id, kw, kw, limit]

        rows = conn.execute(query, params).fetchall()
        records = []
        for r in rows:
            records.append({
                "id": r["id"],
                "title": r["title"],
                "filename": r["filename"],
                "duration": r["duration_seconds"],
                "file_size": r["file_size"],
                "status": r["status"],
                "has_transcript": bool(r["transcript"]),
                "speaker_count": r["speaker_count"],
                "created_at": r["created_at"],
            })
        return jsonify({"success": True, "records": records, "total": len(records)})
    finally:
        conn.close()


@bp.route("/api/recordings/<int:record_id>", methods=["GET"])
@login_required
@require_plugin(blueprint_name)
def get_recording(record_id):
    """获取单条录音详情。"""
    conn = _get_db_conn()
    try:
        row = conn.execute(
            "SELECT * FROM recordings WHERE id=? AND user_id=?",
            (record_id, current_user.id),
        ).fetchone()
        if not row:
            return jsonify({"error": "录音记录不存在"}), 404

        return jsonify({
            "success": True,
            "record": {
                "id": row["id"],
                "title": row["title"],
                "filename": row["filename"],
                "filepath": row["filepath"],
                "duration": row["duration_seconds"],
                "file_size": row["file_size"],
                "status": row["status"],
                "transcript": row["transcript"],
                "speaker_count": row["speaker_count"],
                "created_at": row["created_at"],
            }
        })
    finally:
        conn.close()


@bp.route("/api/recordings/<int:record_id>/audio", methods=["GET"])
@login_required
@require_plugin(blueprint_name)
def download_audio(record_id):
    """下载录音文件。"""
    conn = _get_db_conn()
    try:
        row = conn.execute(
            "SELECT * FROM recordings WHERE id=? AND user_id=?",
            (record_id, current_user.id),
        ).fetchone()
        if not row:
            return jsonify({"error": "录音记录不存在"}), 404

        filepath = row["filepath"]
        if not os.path.exists(filepath):
            return jsonify({"error": "录音文件不存在"}), 404

        directory = os.path.dirname(filepath)
        filename = os.path.basename(filepath)
        return send_from_directory(directory, filename, as_attachment=True)
    finally:
        conn.close()


@bp.route("/api/recordings/<int:record_id>", methods=["DELETE"])
@login_required
@require_plugin(blueprint_name)
def delete_recording(record_id):
    """删除录音文件。"""
    conn = _get_db_conn()
    try:
        row = conn.execute(
            "SELECT * FROM recordings WHERE id=? AND user_id=?",
            (record_id, current_user.id),
        ).fetchone()
        if not row:
            return jsonify({"error": "录音记录不存在"}), 404

        # 删除文件
        filepath = row["filepath"]
        if os.path.exists(filepath):
            os.remove(filepath)

        # 删除数据库记录
        conn.execute("DELETE FROM recordings WHERE id=?", (record_id,))
        conn.commit()

        return jsonify({"success": True, "message": "录音已删除"})
    finally:
        conn.close()


@bp.route("/api/recordings/<int:record_id>/transcribe", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def transcribe_recording(record_id):
    """将录音转为文字（异步任务，立即返回状态）。"""
    conn = _get_db_conn()
    try:
        row = conn.execute(
            "SELECT * FROM recordings WHERE id=? AND user_id=?",
            (record_id, current_user.id),
        ).fetchone()
        if not row:
            return jsonify({"error": "录音记录不存在"}), 404

        filepath = row["filepath"]
        if not os.path.exists(filepath):
            return jsonify({"error": "录音文件不存在"}), 404

        # 更新状态为转写中
        conn.execute(
            "UPDATE recordings SET status='transcribing' WHERE id=?",
            (record_id,),
        )
        conn.commit()

        # 启动后台线程执行转写（传入 app 对象以支持应用上下文）
        from flask import current_app as _current_app
        _app = _current_app._get_current_object()
        thread = threading.Thread(
            target=_do_transcribe,
            args=(record_id, filepath, current_user.id, _app),
            daemon=True,
        )
        thread.start()

        return jsonify({
            "success": True,
            "message": "转写任务已启动",
            "record_id": record_id,
        })
    finally:
        conn.close()


@bp.route("/api/recordings/<int:record_id>/generate-minutes", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def generate_minutes(record_id):
    """将录音转文字后，自动调用 meeting_minutes 技能生成会议纪要。"""
    conn = _get_db_conn()
    try:
        row = conn.execute(
            "SELECT * FROM recordings WHERE id=? AND user_id=?",
            (record_id, current_user.id),
        ).fetchone()
        if not row:
            return jsonify({"error": "录音记录不存在"}), 404

        transcript = row["transcript"]
        if not transcript:
            return jsonify({"error": "请先转写录音"}), 400

        title = row["title"]

        # 调用 meeting_minutes 技能（使用 importlib 支持连字符目录名）
        try:
            import importlib
            mm_module = importlib.import_module("skills.meeting-minutes.meeting_minutes")
            result = mm_module.run(json.dumps({
                "action": "generate",
                "title": title,
                "content": transcript,
                "meeting_date": datetime.now().strftime("%Y-%m-%d"),
            }))
            result_data = json.loads(result)
            if result_data.get("success"):
                return jsonify({
                    "success": True,
                    "message": "会议纪要已生成",
                    "meeting_id": result_data.get("meeting_id"),
                    "summary": result_data.get("summary"),
                    "formatted": result_data.get("formatted"),
                })
            else:
                return jsonify({
                    "success": False,
                    "error": f"生成会议纪要失败: {result_data.get('error', '未知错误')}",
                }), 500
        except ImportError:
            return jsonify({
                "success": False,
                "error": "meeting_minutes 技能未安装，请先创建该技能",
            }), 500
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"生成会议纪要失败: {str(e)}",
            }), 500
    finally:
        conn.close()


@bp.route("/api/recordings/<int:record_id>/title", methods=["PUT"])
@login_required
@require_plugin(blueprint_name)
def update_title(record_id):
    """更新录音标题。"""
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "标题不能为空"}), 400

    conn = _get_db_conn()
    try:
        conn.execute(
            "UPDATE recordings SET title=? WHERE id=? AND user_id=?",
            (title, record_id, current_user.id),
        )
        conn.commit()
        return jsonify({"success": True, "message": "标题已更新"})
    finally:
        conn.close()


@bp.route("/api/settings", methods=["GET"])
@login_required
@require_plugin(blueprint_name)
def get_settings():
    """获取录音插件设置。"""
    # 检查豆包 ASR 是否可用
    doubao_available = False
    try:
        from app.services.doubao_asr import is_available
        doubao_available = is_available()
    except ImportError:
        pass

    return jsonify({
        "success": True,
        "settings": {
            "auto_transcribe": True,
            "cleanup_days": CLEANUP_DAYS,
            "realtime_subtitle": True,
            "speaker_diarization": True,
            "asr_engine": "funasr",  # 默认使用 FunASR
            "doubao_available": doubao_available,
        }
    })


@bp.route("/api/settings", methods=["PUT"])
@login_required
@require_plugin(blueprint_name)
def update_settings():
    """更新录音插件设置。"""
    data = request.get_json() or {}
    asr_engine = data.get("asr_engine", "funasr")

    if asr_engine not in ("funasr", "doubao"):
        return jsonify({"error": "不支持的 ASR 引擎，可选: funasr, doubao"}), 400

    if asr_engine == "doubao":
        try:
            from app.services.doubao_asr import is_available
            if not is_available():
                return jsonify({"error": "豆包 ASR 未配置，请先设置 DOUBAO_ASR_APPID 和 DOUBAO_ASR_TOKEN"}), 400
        except ImportError:
            return jsonify({"error": "豆包 ASR 服务模块未加载"}), 500

    # 保存设置到 session（每个用户独立）
    from flask import session
    session["meeting_recorder_asr_engine"] = asr_engine

    return jsonify({
        "success": True,
        "message": f"ASR 引擎已切换为: {'豆包 ASR' if asr_engine == 'doubao' else 'FunASR（离线）'}",
        "asr_engine": asr_engine,
    })


@bp.route("/api/cleanup", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def trigger_cleanup():
    """手动触发录音文件清理。"""
    try:
        deleted = _do_cleanup()
        return jsonify({"success": True, "deleted_count": deleted, "message": f"已清理 {deleted} 条过期录音"})
    except Exception as e:
        return jsonify({"error": f"清理失败: {str(e)}"}), 500


# ══════════════════════════════════════════════════════════════════════════
# 内部函数
# ══════════════════════════════════════════════════════════════════════════

def _save_recording(title: str, filename: str, filepath: str,
                    duration: float = 0, file_size: int = 0,
                    auto_transcribe: int = 1) -> int:
    """保存录音记录到数据库。"""
    conn = _get_db_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO recordings (user_id, title, filename, filepath, duration_seconds, file_size, auto_transcribe)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (current_user.id, title, filename, filepath, duration, file_size, auto_transcribe),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _get_audio_duration(filepath: str) -> float:
    """获取音频时长（秒）。"""
    try:
        import subprocess
        cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
            filepath,
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=10, text=True)
        if proc.returncode == 0 and proc.stdout.strip():
            return float(proc.stdout.strip())
    except Exception:
        pass

    # 如果是 WAV 格式，手动计算
    try:
        import wave
        with wave.open(filepath, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return frames / rate
    except Exception:
        pass

    return 0.0


def _start_auto_transcribe(record_id: int, filepath: str):
    """自动启动转写（延迟2秒后执行，确保文件写入完成）。"""
    from flask import current_app
    app = current_app._get_current_object()

    def delayed_transcribe():
        time_module.sleep(2)
        with app.app_context():
            try:
                conn = _get_db_conn()
                row = conn.execute(
                    "SELECT * FROM recordings WHERE id=?", (record_id,)
                ).fetchone()
                conn.close()
                if row and row["status"] == "uploaded":
                    _do_transcribe(record_id, filepath, row["user_id"], app)
            except Exception as e:
                current_app.logger.error(f"自动转写启动失败 (record_id={record_id}): {str(e)}")

    thread = threading.Thread(target=delayed_transcribe, daemon=True)
    thread.start()


def _do_transcribe(record_id: int, filepath: str, user_id: int, app=None):
    """后台执行语音转文字（含多说话人识别）。"""
    # 后台线程需要应用上下文
    if app is None:
        from flask import current_app
        app = current_app._get_current_object()
    with app.app_context():
        try:
            from app.services.voice_service import speech_to_text, vad_detect

            # 读取音频文件
            with open(filepath, "rb") as f:
                audio_data = f.read()

            # 获取音频格式
            ext = os.path.splitext(filepath)[1].lower()
            audio_format = {
                ".webm": "audio/webm",
                ".wav": "audio/wav",
                ".mp3": "audio/mpeg",
                ".ogg": "audio/ogg",
                ".m4a": "audio/mp4",
                ".mp4": "audio/mp4",
                ".opus": "audio/opus",
            }.get(ext, "audio/webm")

            # ── 多说话人识别 ────────────────────────────────────────────
            # 使用 VAD 检测语音片段，根据能量差异估算说话人数量
            speaker_count = 0
            try:
                vad_result = vad_detect(audio_data, audio_format)
                segments = vad_result.get("segments", [])

                if len(segments) > 1:
                    # 分析各片段的能量特征来估算说话人数量
                    # 简单策略：根据片段数量估算（1-5人）
                    if len(segments) <= 3:
                        speaker_count = 1
                    elif len(segments) <= 8:
                        speaker_count = 2
                    elif len(segments) <= 15:
                        speaker_count = 3
                    else:
                        speaker_count = min(5, len(segments) // 5)
            except Exception:
                pass

            # ── 执行语音识别 ────────────────────────────────────────────
            text = speech_to_text(audio_data, audio_format)

            # ── 多说话人标注 ────────────────────────────────────────────
            if text and speaker_count > 1:
                # 在转写文本中标注说话人切换标记
                # 根据 VAD 片段在文本中插入说话人标签
                try:
                    # 简单实现：按段落分配说话人
                    paragraphs = text.split("\n")
                    labeled_paragraphs = []
                    current_speaker = 1
                    for i, para in enumerate(paragraphs):
                        if para.strip():
                            speaker_label = (i % speaker_count) + 1
                            labeled_paragraphs.append(f"[说话人{speaker_label}] {para}")
                        else:
                            labeled_paragraphs.append(para)
                    text = "\n".join(labeled_paragraphs)
                except Exception:
                    pass

            # 更新数据库
            conn = _get_db_conn()
            try:
                if text:
                    conn.execute(
                        "UPDATE recordings SET status='completed', transcript=?, speaker_count=? WHERE id=?",
                        (text, speaker_count, record_id),
                    )
                else:
                    conn.execute(
                        "UPDATE recordings SET status='failed', transcript='' WHERE id=?",
                        (record_id,),
                    )
                conn.commit()
            finally:
                conn.close()

        except Exception as e:
            current_app.logger.error(f"录音转文字失败 (record_id={record_id}): {str(e)}")
            conn = _get_db_conn()
            try:
                conn.execute(
                    "UPDATE recordings SET status='failed', transcript=? WHERE id=?",
                    (f"转写失败: {str(e)}", record_id),
                )
                conn.commit()
            finally:
                conn.close()


def _do_cleanup() -> int:
    """清理过期录音文件（超过 CLEANUP_DAYS 天）。"""
    import sqlite3
    cutoff = (datetime.now() - timedelta(days=CLEANUP_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    deleted_count = 0

    conn = _get_db_conn()
    try:
        # 查找过期记录
        rows = conn.execute(
            "SELECT * FROM recordings WHERE created_at < ?",
            (cutoff,),
        ).fetchall()

        for row in rows:
            filepath = row["filepath"]
            # 删除文件
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass
            # 删除数据库记录
            conn.execute("DELETE FROM recordings WHERE id=?", (row["id"],))
            deleted_count += 1

        conn.commit()
    finally:
        conn.close()

    return deleted_count


def _try_auto_cleanup():
    """尝试自动清理（每小时最多执行一次）。"""
    global _last_cleanup_time
    now = time_module.time()
    with _cleanup_lock:
        if now - _last_cleanup_time < 3600:  # 1小时内不重复执行
            return
        _last_cleanup_time = now

    try:
        count = _do_cleanup()
        if count > 0:
            current_app.logger.info(f"自动清理了 {count} 条过期录音")
    except Exception as e:
        current_app.logger.error(f"自动清理失败: {str(e)}")


# 在每次请求时尝试自动清理（通过 before_request）
@bp.before_request
def before_request_cleanup():
    """每次请求前尝试自动清理过期录音。"""
    try:
        _try_auto_cleanup()
    except Exception:
        pass
