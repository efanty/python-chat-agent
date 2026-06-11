// ── CSRF Token ────────────────────────────────────────────────
function getCSRFToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

// ── Global state ──────────────────────────────────────────────
// convId is initialized from the Jinja2 template (index.html)
let isStreaming = false;

let abortController = null;

function setInputEnabled(enabled) {
    const textarea = document.getElementById('messageInput');
    const sendBtn = document.querySelector('.btn-send');
    const fileBtn = document.querySelector('.btn-file');
    const fileInput = document.getElementById('fileInput');
    if (textarea) textarea.disabled = !enabled;
    if (sendBtn) {
        if (enabled) {
            sendBtn.disabled = false;
            sendBtn.classList.remove('btn-stop');
            sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i> 发送';
            sendBtn.onclick = null;
        } else {
            sendBtn.disabled = false;
            sendBtn.classList.add('btn-stop');
            sendBtn.innerHTML = '<i class="fas fa-stop-circle"></i> 停止';
            sendBtn.onclick = function(e) { e.preventDefault(); stopStreaming(); };
        }
    }
    if (fileBtn) fileBtn.disabled = !enabled;
    if (fileInput) fileInput.disabled = !enabled;
    if (textarea && enabled) textarea.focus();
}

function stopStreaming() {
    if (abortController) {
        abortController.abort();
        abortController = null;
    }
}

function updateAgentDesc() {
    const sel = document.getElementById('agentSelect');
    const desc = document.getElementById('agentDesc');
    if (!sel || !desc) return;
    const option = sel.options[sel.selectedIndex];
    if (option && option.dataset.description && option.value) {
        desc.textContent = option.dataset.description;
    } else {
        desc.textContent = '';
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    updateAgentDesc();
    var m = document.getElementById('chatMessages');
    if(m) addCodeCopyButtons(m);
    // 文件选择后显示文件名
    var fi = document.getElementById('fileInput');
    var fa = document.getElementById('fileAttachment');
    if (fi && fa) {
        fi.addEventListener('change', function() {
            var names = [];
            for (var i = 0; i < fi.files.length; i++) {
                names.push(fi.files[i].name);
            }
            if (names.length > 0) {
                fa.textContent = names.join(', ');
                fa.style.display = 'inline-flex';
            } else {
                fa.style.display = 'none';
                fa.textContent = '';
            }
        });
    }
});

function addSidebarItem(id, title) {
    const list = document.getElementById('convList');
    const emptyMsg = list.querySelector('.conv-empty');
    if (emptyMsg) emptyMsg.remove();
    if (list.querySelector(`.conv-item[data-id="${id}"]`)) return;
    const div = document.createElement('div');
    div.className = 'conv-item';
    div.dataset.id = id;
    div.onclick = function() { loadConversation(id); };
    div.innerHTML = `<span class="conv-title">${escapeHtml(title || '新对话')}</span>
        <span class="conv-actions">
            <button class="btn btn-sm btn-outline-light" onclick="event.stopPropagation();renameConversation(${id})" title="重命名"><i class="fas fa-pen"></i></button>
            <button class="btn btn-sm btn-outline-danger" onclick="event.stopPropagation();deleteConversation(${id})" title="删除"><i class="fas fa-trash"></i></button>
        </span>`;
    list.prepend(div);
    switchSidebarConversation(id);
}

function switchSidebarConversation(id) {
    const list = document.getElementById('convList');
    list.querySelectorAll('.conv-item').forEach(el => el.classList.remove('active'));
    const item = list.querySelector(`.conv-item[data-id="${id}"]`);
    if (item) item.classList.add('active');
}

function removeSidebarItem(id) {
    const item = document.querySelector(`.conv-item[data-id="${id}"]`);
    if (item) item.remove();
}

function updateSidebarTitle(id, title) {
    const item = document.querySelector(`.conv-item[data-id="${id}"] .conv-title`);
    if (item) item.textContent = title;
}

async function loadConversation(id) {
    try {
        const resp = await fetch("/chat/conversation/" + id);
        if (!resp.ok) return;
        const data = await resp.json();
        convId = id;
        document.getElementById('convIdInput').value = id;
        switchSidebarConversation(id);
        document.getElementById('exportBtn').style.display = '';
        const container = document.getElementById('chatMessages');
        container.innerHTML = '';
        for (const msg of data.messages || []) {
            appendMessageBubble(container, msg.role, msg.content, msg.created_at, msg);
        }
        container.scrollTop = container.scrollHeight;
    } catch(err) {
        console.error('Failed to load conversation:', err);
    }
}

async function newConversation() {
    const agentId = document.getElementById('agentSelect').value;
    const modelId = document.getElementById('modelSelect').value;
    try {
        const resp = await fetch(window.CHAT_URLS.new_conversation, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken()},
            body: JSON.stringify({agent_id: agentId || null, model_id: modelId || null})
        });
        const data = await resp.json();
        convId = data.id;
        document.getElementById('convIdInput').value = data.id;
        document.getElementById('exportBtn').style.display = '';
        document.getElementById('chatMessages').innerHTML = '';
        addSidebarItem(data.id, data.title || '新对话');
    } catch(err) {
        console.error('Failed to create conversation:', err);
    }
}

function deleteConversation(id) {
    if (!confirm('确定删除此对话？')) return;
    fetch("/chat/conversation/" + id + "/delete", {method: 'POST', headers: {'X-CSRFToken': getCSRFToken()}}).then(() => {
        removeSidebarItem(id);
        if (convId == id) {
            convId = null;
            document.getElementById('convIdInput').value = '';
            document.getElementById('exportBtn').style.display = 'none';
            document.getElementById('chatMessages').innerHTML =
                '<div class="text-center text-muted" style="padding-top: 100px;">' +
                '<i class="fas fa-robot" style="font-size:3rem;"></i>' +
                '<p class="mt-3">选择智能体和模型，开始对话</p></div>';
        }
    });
}

function renameConversation(id) {
    const title = prompt('新名称：');
    if (!title) return;
    fetch("/chat/conversation/" + id + "/rename", {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken()},
        body: JSON.stringify({title: title})
    }).then(() => updateSidebarTitle(id, title));
}

function updatePreferences() {
    const agentId = document.getElementById('agentSelect').value;
    const modelId = document.getElementById('modelSelect').value;
    fetch(window.CHAT_URLS.user_settings, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken()},
        body: JSON.stringify({preferred_agent_id: agentId || null, preferred_model_id: modelId || null})
    });
}

async function sendMessage(event) {
    event.preventDefault();
    if (isStreaming) return;
    const content = document.getElementById('messageInput').value.trim();
    const fileInput = document.getElementById('fileInput');
    if (!content && !fileInput.files[0]) return;

    const agentSelect = document.getElementById('agentSelect');
    const modelSelect = document.getElementById('modelSelect');
    if (!agentSelect.value || !modelSelect.value) {
        const missing = [];
        if (!agentSelect.value) missing.push('智能体');
        if (!modelSelect.value) missing.push('模型');
        alert('请先选择' + missing.join('和') + '后再发送消息。');
        return;
    }

    const formData = new FormData();
    formData.append('conversation_id', document.getElementById('convIdInput').value);
    formData.append('content', content);
    formData.append('agent_id', document.getElementById('agentSelect').value);
    formData.append('model_id', document.getElementById('modelSelect').value);
    formData.append('csrf_token', getCSRFToken());

    const files = fileInput.files;
    const uploadedFileNames = [];
    for (let i = 0; i < files.length; i++) {
        formData.append('file', files[i]);
        uploadedFileNames.push(files[i].name);
    }

    document.getElementById('messageInput').value = '';
    document.getElementById('messageInput').style.height = 'auto';
    if (fileInput) { fileInput.value = ''; }
    const fileAttachment = document.getElementById('fileAttachment');
    if (fileAttachment) { fileAttachment.style.display = 'none'; fileAttachment.textContent = ''; }

    const chatMessages = document.getElementById('chatMessages');

    const userBubble = document.createElement('div');
    userBubble.className = 'message-row user';
    let userContent = escapeHtml(content);
    if (uploadedFileNames.length > 0) {
        const fileBadges = uploadedFileNames.map(function(name) {
            return `<div class="file-attachment-badge"><i class="fas fa-paperclip"></i> ${escapeHtml(name)}</div>`;
        }).join('');
        userContent = fileBadges + '<br/>' + userContent;
    }
    const nowTime = new Date().toLocaleString('zh-CN', {hour:'2-digit', minute:'2-digit', year:'numeric', month:'2-digit', day:'2-digit'});
    userBubble.innerHTML = `<div class="message-bubble"><div>${userContent}</div><div class="message-meta"><span class="message-time">${nowTime}</span><button class="btn-copy" onclick="copyMsg(this)" title="复制"><i class="fas fa-copy"></i></button></div></div>`;
    chatMessages.appendChild(userBubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    const aiBubble = document.createElement('div');
    aiBubble.className = 'message-row assistant';
    aiBubble.innerHTML = `<div class="message-bubble"><div class="ai-content markdown-body"><span class="cursor-blink">▌</span></div><div class="message-meta"><span class="message-time">${nowTime}</span>&nbsp;<span class="msg-usage"></span><button class="btn-copy" onclick="copyMsg(this)" title="复制"><i class="fas fa-copy"></i></button></div></div>`;
    chatMessages.appendChild(aiBubble);
    const aiContent = aiBubble.querySelector('.ai-content');
    const aiMeta = aiBubble.querySelector('.msg-usage');
    chatMessages.scrollTop = chatMessages.scrollHeight;

    let toolGroup = null;
    let toolCount = 0;

    isStreaming = true;
    setInputEnabled(false);

    if (typeof marked !== 'undefined') {
        marked.setOptions({breaks: true, gfm: true});
    }

    let buffer = '';
    let fullText = '';
    try {
        abortController = new AbortController();
        const response = await fetch(window.CHAT_URLS.stream_message, {
            method: 'POST',
            body: formData,
            signal: abortController.signal,
        });

        if (!response.ok) {
            const contentType = response.headers.get('content-type') || '';
            if (contentType.includes('application/json')) {
                const errData = await response.json();
                aiContent.innerHTML = '<span class="text-danger">' + escapeHtml(errData.error || '请求失败') + '</span>';
            } else {
                const errText = await response.text();
                aiContent.innerHTML = '<span class="text-danger">请求失败：' + escapeHtml(errText) + '</span>';
            }
            isStreaming = false;
            setInputEnabled(true);
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, {stream: true});
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.chunk) {
                            fullText += data.chunk;
                            const html = typeof marked !== 'undefined'
                                ? marked.parse(fullText)
                                : escapeHtml(fullText).replace(/\n/g, '<br>');
                            aiContent.innerHTML = html + '<span class="cursor-blink">▌</span>';
                        }
                        if (data.tool_call) {
                            toolCount++;
                            if (!toolGroup) {
                                toolGroup = document.createElement('div');
                                toolGroup.className = 'message-row assistant tool-wrapper';
                                toolGroup.innerHTML = `
                                    <div class="message-bubble tool-toggle-bubble" onclick="toggleToolDetails(this)">
                                        <i class="fas fa-cog fa-spin"></i> <span class="tool-count-label">工具调用 (${toolCount})</span>
                                        <i class="fas fa-chevron-down tool-chevron"></i>
                                    </div>
                                    <div class="tool-details" style="display:none;"></div>
                                `;
                                chatMessages.appendChild(toolGroup);
                            } else {
                                const label = toolGroup.querySelector('.tool-count-label');
                                if (label) label.textContent = `工具调用 (${toolCount})`;
                            }
                            const details = toolGroup.querySelector('.tool-details');
                            const entry = document.createElement('div');
                            entry.className = 'message-bubble tool-call-entry';
                            entry.innerHTML = `<i class="fas fa-cog"></i> <strong>${escapeHtml(data.tool_call)}</strong><span class="tool-pending"> 执行中...</span>`;
                            entry.setAttribute('data-tool-name', data.tool_call);
                            details.appendChild(entry);
                        }
                        if (data.tool_result && toolGroup) {
                            const details = toolGroup.querySelector('.tool-details');
                            const entry = details.querySelector(`[data-tool-name="${escapeHtml(data.tool_result.name)}"]`);
                            const resultText = (data.tool_result.result || '').substring(0, 500);
                            if (entry) {
                                entry.innerHTML = `
                                    <i class="fas fa-check-circle"></i> <strong>${escapeHtml(data.tool_result.name)}</strong>
                                    <pre class="tool-result-pre">${escapeHtml(resultText)}</pre>
                                `;
                            }
                        }
                        if (data.conv_id) {
                            if (!convId) {
                                convId = data.conv_id;
                                document.getElementById('convIdInput').value = data.conv_id;
                                document.getElementById('exportBtn').style.display = '';
                                addSidebarItem(data.conv_id, data.title || '新对话');
                            } else if (data.title && data.title !== '新对话') {
                                updateSidebarTitle(data.conv_id, data.title);
                            }
                        }
                        if (data.done) {
                            if (toolGroup) {
                                const spinner = toolGroup.querySelector('.fa-spin');
                                if (spinner) spinner.className = 'fas fa-check-circle';
                                const label = toolGroup.querySelector('.tool-count-label');
                                if (label) label.textContent = `工具调用 (${toolCount})`;
                            }
                            const html = typeof marked !== 'undefined'
                                ? marked.parse(fullText)
                                : escapeHtml(fullText).replace(/\n/g, '<br>');
                            aiContent.innerHTML = html;
                            addCodeCopyButtons(aiContent);
                            if (data.usage && data.usage.input_tokens + data.usage.output_tokens > 0) {
                                const displayCost = data.cost !== undefined ? data.cost : 0;
                                aiMeta.textContent = `${data.usage.input_tokens}+${data.usage.output_tokens} tokens · ¥${displayCost}`;
                            } else {
                                aiMeta.textContent = '';
                            }
                            if (window.ttsEnabled && fullText) {
                                speakText(fullText);
                            }
                        }
                        if (data.error) {
                            aiContent.innerHTML = `<span class="text-danger">错误：${escapeHtml(data.error)}</span>`;
                        }
                    } catch(e) {}
                }
            }
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    } catch(err) {
        if (err.name === 'AbortError') {
            if (fullText) {
                const html = typeof marked !== 'undefined'
                    ? marked.parse(fullText)
                    : escapeHtml(fullText).replace(/\n/g, '<br>');
                aiContent.innerHTML = html;
                addCodeCopyButtons(aiContent);
            } else {
                aiContent.innerHTML = '<span class="text-muted">[已停止]</span>';
            }
        } else {
            aiContent.innerHTML = `<span class="text-danger">连接错误：${escapeHtml(err.message)}</span>`;
        }
    } finally {
        isStreaming = false;
        abortController = null;
        if (toolGroup) {
            const spinner = toolGroup.querySelector('.fa-spin');
            if (spinner) spinner.className = 'fas fa-minus-circle';
            const label = toolGroup.querySelector('.tool-count-label');
            if (label && !label.textContent.includes('(')) {
                label.textContent = `工具调用 (已停止)`;
            }
        }
        setInputEnabled(true);
    }
}

function toggleToolDetails(toggleEl) {
    const wrapper = toggleEl.parentElement;
    const details = wrapper.querySelector('.tool-details');
    const icon = toggleEl.querySelector('.tool-chevron');
    if (details.style.display === 'none') {
        details.style.display = 'block';
        if (icon) { icon.style.transform = 'rotate(180deg)'; }
    } else {
        details.style.display = 'none';
        if (icon) { icon.style.transform = 'rotate(0deg)'; }
    }
}

function copyMsg(btn) {
    const bubble = btn.closest('.message-bubble');
    const content = bubble.querySelector('.markdown-body') || bubble.querySelector('div:first-child');
    const text = content ? content.innerText : '';
    const icon = btn.querySelector('i');
    const done = () => {
        icon.className = 'fas fa-check';
        setTimeout(() => { icon.className = 'fas fa-copy'; }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(() => {});
    } else {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed'; ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); done(); } catch(e) {}
        document.body.removeChild(ta);
    }
}

function addCodeCopyButtons(container) {
    if (!container) return;
    container.querySelectorAll('pre').forEach(function(pre) {
        if (pre.parentElement?.classList.contains('md-code-block')) return;
        var code = pre.querySelector('code');
        var lang = 'code';
        if (code && code.className) {
            var m = code.className.match(/language-(\w+)/);
            if (m) lang = m[1];
        }
        var textToCopy = code ? code.innerText : pre.innerText;
        var wrapper = document.createElement('div');
        wrapper.className = 'md-code-block md-code-block-light';
        var banner = document.createElement('div');
        banner.className = 'md-code-block-banner-wrap';
        banner.innerHTML = '<div class="md-code-block-banner md-code-block-banner-lite">' +
            '<div style="display:flex;align-items:center;justify-content:space-between;width:100%;">' +
            '<div style="display:flex;align-items:center;gap:8px;">' +
            '<span class="code-block-lang">' + escapeHtml(lang) + '</span>' +
            '</div>' +
            '<div class="code-block-actions">' +
            '<button class="btn btn-sm btn-outline-light ms-auto me-1" onclick="copyCodeBlock(this)" title="复制代码">' +
            '<i class="fas fa-copy"></i>' +
            '<span>复制</span>' +
            '</button>' +
            '<button class="btn btn-sm btn-outline-success ms-auto me-1" onclick="downloadCodeBlock(this)" title="下载代码">' +
            '<i class="fas fa-download"></i>' +
            '<span>下载</span>' +
            '</button>' +
            '</div>' +
            '</div>';
        pre.parentNode.insertBefore(wrapper, pre);
        wrapper.appendChild(banner);
        wrapper.appendChild(pre);
    });
}

function copyCodeBlock(btn) {
    var wrapper = btn.closest('.md-code-block');
    var code = wrapper ? wrapper.querySelector('pre code') : null;
    var text = code ? code.innerText : '';
    btn.classList.add('copied');
    var ico = btn.querySelector('i');
    if (ico) { ico.className = 'fas fa-check'; }
    var span = btn.querySelector('span');
    if (span) span.textContent = '已复制';
    setTimeout(function() {
        btn.classList.remove('copied');
        if (ico) { ico.className = 'fas fa-copy'; }
        if (span) span.textContent = '复制';
    }, 2000);
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text);
    } else {
        var ta = document.createElement('textarea');
        ta.value = text; ta.style.position = 'fixed'; ta.style.left = '-9999px';
        document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); } catch(e) {}
        document.body.removeChild(ta);
    }
}

function downloadCodeBlock(btn) {
    var wrapper = btn.closest('.md-code-block');
    var code = wrapper ? wrapper.querySelector('pre code') : null;
    var text = code ? code.innerText : '';
    var langEl = wrapper ? wrapper.querySelector('.code-block-lang') : null;
    var ext = (langEl ? langEl.textContent : 'txt').split('-')[0];
    var extMap = {'python':'py','javascript':'js','typescript':'ts','html':'html','css':'css','json':'json','xml':'xml','yaml':'yaml','markdown':'md','shell':'sh','bash':'sh','sql':'sql','dockerfile':'Dockerfile'};
    var fext = extMap[ext] || ext || 'txt';
    var blob = new Blob([text], {type:'text/plain;charset=utf-8'});
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = 'code.' + fext;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    btn.classList.add('downloaded');
    var ico = btn.querySelector('i');
    if (ico) { ico.className = 'fas fa-check'; }
    var span = btn.querySelector('span');
    if (span) span.textContent = '已下载';
    setTimeout(function() {
        btn.classList.remove('downloaded');
        if (ico) { ico.className = 'fas fa-download'; }
        if (span) span.textContent = '下载';
    }, 2000);
}

function appendMessageBubble(container, role, content, createdAt, extra) {
    const row = document.createElement('div');
    row.className = 'message-row ' + role;
    const time = createdAt
        ? new Date(createdAt).toLocaleString('zh-CN', {hour:'2-digit',minute:'2-digit',year:'numeric',month:'2-digit',day:'2-digit'})
        : '';
    let bodyContent = escapeHtml(content || '');
    let fileBadge = '';
    if (extra && extra.file_name) {
        fileBadge = `<div class="mb-1 file-attachment-badge"><i class="fas fa-paperclip"></i> ${escapeHtml(extra.file_name)}</div><br/>`;
    }
    if (role === 'assistant') {
        bodyContent = `<div class="markdown-body">${marked ? marked.parse(content || '') : bodyContent}</div>`;
    } else {
        bodyContent = `<div>${bodyContent}</div>`;
    }
    const usage = (extra && extra.token_count && extra.token_count > 0)
        ? `<span class="msg-usage">${extra.input_tokens || 0}+${extra.output_tokens || 0} tokens${extra.cost ? ' · ¥' + Number(extra.cost).toFixed(4) : ''}</span>`
        : '';
    row.innerHTML = `<div class="message-bubble">${fileBadge}${bodyContent}
        <div class="message-meta">
            <span class="message-time">${time}</span>
            ${usage}
            <button class="btn-copy" onclick="copyMsg(this)" title="复制"><i class="fas fa-copy"></i></button>
        </div></div>`;
    var mdBody = row.querySelector('.markdown-body');
    if (mdBody) addCodeCopyButtons(mdBody);
    container.appendChild(row);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function exportConversation() {
    const rows = document.querySelectorAll('#chatMessages .message-row');
    if (!rows.length) return;
    const titleEl = document.querySelector('#agentSelect option:checked');
    const agentName = titleEl ? titleEl.textContent : '对话';
    const now = new Date();
    const dateStr = now.toLocaleDateString('zh-CN') + ' ' + now.toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'});
    let bodyHtml = '';
    for (const row of rows) {
        const isUser = row.classList.contains('user');
        const roleLabel = isUser ? '你' : 'AI';
        const bubble = row.querySelector('.message-bubble');
        if (!bubble) continue;
        if (row.classList.contains('tool-wrapper')) continue;
        const contentEl = bubble.querySelector('.markdown-body') || bubble.querySelector('div:first-child');
        const contentHtml = contentEl ? contentEl.innerHTML : '';
        const timeEl = bubble.querySelector('.message-time');
        const time = timeEl ? timeEl.textContent : '';
        const align = isUser ? 'right' : 'left';
        const bgColor = isUser ? '#6366f1' : '#1e293b';
        const border = isUser ? '' : 'border:1px solid #334155;';
        bodyHtml += `
        <div style="display:flex;margin-bottom:16px;justify-content:${align}">
            <div style="max-width:80%;background:${bgColor};${border}padding:10px 16px;border-radius:14px;${isUser ? 'border-bottom-right-radius:4px' : 'border-bottom-left-radius:4px'};line-height:1.6;font-size:14px;word-break:break-word">
                <div style="font-size:11px;color:${isUser ? 'rgba(255,255,255,0.7)' : '#94a3b8'};margin-bottom:4px">${escapeHtml(roleLabel)}</div>
                <div>${contentHtml}</div>
                <div style="font-size:11px;color:${isUser ? 'rgba(255,255,255,0.5)' : '#94a3b8'};margin-top:6px;text-align:${align}">${escapeHtml(time)}</div>
            </div>
        </div>`;
    }
    const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${escapeHtml(agentName)} - 导出对话</title>
<style>
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:'Segoe UI',system-ui,-apple-system,sans-serif; background:#0f172a; color:#e2e8f0; padding:20px; }
.header { text-align:center; padding:20px 0 30px; border-bottom:1px solid #334155; margin-bottom:24px; }
.header h1 { font-size:18px; color:#fff; margin-bottom:4px; }
.header .meta { font-size:12px; color:#94a3b8; }
.messages { max-width:800px; margin:0 auto; }
.markdown-body { line-height:1.7; }
.markdown-body p { margin:4px 0 8px; }
.markdown-body pre { background:#0f172a; padding:12px; border-radius:8px; overflow-x:auto; font-size:13px; margin:8px 0; }
.markdown-body code { background:rgba(99,102,241,0.15); padding:2px 6px; border-radius:4px; font-size:13px; }
.markdown-body pre { background:#0f172a; padding:0; border-radius:8px; overflow:hidden; margin:8px 0; }
.markdown-body pre code { background:none; padding:12px 16px; color:#e2e8f0; display:block; overflow-x:auto; font-size:13px; line-height:1.6; }
.md-code-block { border-radius:8px; overflow:hidden; margin:8px 0; border:1px solid #334155; }
.md-code-block pre { margin:0; border-radius:0 0 8px 8px; border:none; }
.md-code-block-banner-wrap { width:100%; }
.md-code-block-banner {
  display:flex; align-items:center; justify-content:space-between;
  background:#1e293b; padding:4px 12px; border-bottom:1px solid #334155; border-left:3px solid rgba(99,102,241,0.4);
  font-size:12px; color:#94a3b8;
}
.code-block-lang { font-size:11px; color:#818cf8; font-family:monospace; letter-spacing:0.3px; }
.code-block-actions { display:flex; gap:4px; }
.code-block-actions button {
  display:inline-flex; align-items:center; gap:5px;
  background:transparent; border:none;
  color:#64748b; cursor:pointer; padding:2px 6px; border-radius:4px;
  font-size:12px; transition:all 0.15s; line-height:1;
}
.code-block-actions button:hover {
  background:rgba(99,102,241,0.12); color:#a5b4fc;
}
.code-block-actions button:active { transform:scale(0.95); }
.code-block-actions button.copied,
.code-block-actions button.downloaded {
  background:rgba(16,185,129,0.12); color:#34d399;
}
.code-block-actions button i { font-size:12px; width:12px; text-align:center; }
.code-block-actions button span { font-size:12px; }
</style>
</head>
<body>
<div class="header">
    <h1>${escapeHtml(agentName)}</h1>
    <div class="meta">导出时间: ${escapeHtml(dateStr)}</div>
</div>
<div class="messages">
${bodyHtml}
</div>
</body>
</html>`;
    const blob = new Blob([html], {type: 'text/html;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `对话导出_${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// ── Search modal ──
function showSearchModal() {
    const modal = document.getElementById('searchModal');
    if (modal) {
        modal.style.display = 'block';
        const input = document.getElementById('searchInput');
        if (input) {
            input.value = '';
            setTimeout(() => input.focus(), 100);
        }
        document.getElementById('searchResults').innerHTML = '';
    }
}

function closeSearchModal() {
    const modal = document.getElementById('searchModal');
    if (modal) modal.style.display = 'none';
}

document.addEventListener('click', function(e) {
    const modal = document.getElementById('searchModal');
    if (modal && e.target === modal) closeSearchModal();
});

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeSearchModal();
});

async function performSearch() {
    const input = document.getElementById('searchInput');
    const q = input.value.trim();
    if (!q) return;
    const resultsContainer = document.getElementById('searchResults');
    resultsContainer.innerHTML = '<div class="search-loading"><i class="fas fa-spinner fa-spin"></i> 搜索中...</div>';
    try {
        const resp = await fetch(window.CHAT_URLS.search_conversations, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken()},
            body: JSON.stringify({q: q})
        });
        const data = await resp.json();
        renderSearchResults(data.results, q);
    } catch (err) {
        resultsContainer.innerHTML = '<div class="search-error">搜索出错，请重试</div>';
    }
}

function renderSearchResults(results, query) {
    const container = document.getElementById('searchResults');
    if (!results || results.length === 0) {
        container.innerHTML = '<div class="search-no-results">未找到匹配结果</div>';
        return;
    }
    let html = `<div class="search-stats">共 ${results.length} 个对话包含 "<strong>${escapeHtml(query)}</strong>"</div>`;
    for (const group of results) {
        const conv = group.conversation;
        const title = escapeHtml(conv.title);
        const updated = conv.updated_at ? new Date(conv.updated_at).toLocaleDateString('zh-CN') : '';
        html += `<div class="search-group" data-conv-id="${conv.id}">`;
        html += `<div class="search-group-header" onclick="goToConversation(${conv.id})">
                    <i class="fas fa-comments"></i> ${title}
                    <span class="search-conv-meta">${group.matches.length} 条匹配 · ${updated}</span>
                 </div>`;
        for (const match of group.matches) {
            const roleIcon = match.role === 'user' ? 'fa-user' : 'fa-robot';
            const roleLabel = match.role === 'user' ? '你' : 'AI';
            const snippet = escapeHtml(match.content).substring(0, 150);
            html += `<div class="search-match" onclick="goToConversation(${conv.id})">
                        <span class="search-match-role ${match.role}"><i class="fas ${roleIcon}"></i> ${roleLabel}</span>
                        <span class="search-match-text">${snippet}</span>
                     </div>`;
        }
        html += `</div>`;
    }
    container.innerHTML = html;
}

function goToConversation(id) {
    closeSearchModal();
    loadConversation(id);
}

// ═══════════════════════════════════════════════════════════════
// 语音输入 — MediaRecorder 录音 + VAD 静音检测 + 波形可视化 + 打断
// ═══════════════════════════════════════════════════════════════
let isVoiceRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let audioStream = null;
let audioContext = null;
let analyserNode = null;
let silenceTimer = null;
let isAutoVoiceMode = false;  // 是否处于自动语音对话模式
let ttsRate = '+0%';          // TTS 语速
let ttsPitch = '+0Hz';        // TTS 语调
let ttsStyle = 'general';     // TTS 音色（说话风格）

// 静音检测参数
let SILENCE_THRESHOLD = 0.02;   // 音量阈值（0-1），低于此值视为静音（可配置）
const SILENCE_TIMEOUT_MS = 1500;  // 静音持续多少毫秒后自动停止
const VOICE_IDLE_TIMEOUT_MS = 60000; // 等待用户语音输入的最大时间（60秒）
let voiceIdleTimer = null;        // 用户无语音输入超时定时器
let silenceDetectionEnabled = true; // 静音检测是否启用（刚打开麦克风时暂时禁用）
const SILENCE_DETECTION_DELAY_MS = 3000; // 打开麦克风后延迟多少毫秒才启用静音检测（给用户反应时间）
let silenceDetectionTimer = null;     // 延迟启用静音检测的定时器

// 波形可视化
let waveformCanvas = null;
let waveformCtx = null;
let waveformAnimId = null;

function toggleVoiceInput() {
    const btn = document.getElementById('voiceInputBtn');
    if (!btn) return;
    if (isVoiceRecording) {
        stopVoiceRecording();
        return;
    }
    startVoiceRecording();
}

async function startVoiceRecording() {
    const btn = document.getElementById('voiceInputBtn');
    if (!btn) return;
    try {
        audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioChunks = [];

        // ── 初始化音频分析器用于静音检测 + 波形可视化 ──
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        analyserNode = audioContext.createAnalyser();
        analyserNode.fftSize = 256;
        var source = audioContext.createMediaStreamSource(audioStream);
        source.connect(analyserNode);

        // ── 初始化波形 Canvas ──
        waveformCanvas = document.getElementById('waveformCanvas');
        if (waveformCanvas) {
            waveformCtx = waveformCanvas.getContext('2d');
            document.getElementById('voiceWaveform').style.display = 'block';
        }

        const mimeType = getSupportedMimeType();
        mediaRecorder = new MediaRecorder(audioStream, mimeType ? { mimeType } : {});
        mediaRecorder.ondataavailable = function(event) {
            if (event.data.size > 0) audioChunks.push(event.data);
        };
        mediaRecorder.onstop = function() {
            if (audioStream) {
                audioStream.getTracks().forEach(function(t) { t.stop(); });
                audioStream = null;
            }
            if (audioContext) {
                audioContext.close();
                audioContext = null;
            }
            analyserNode = null;
            if (silenceTimer) {
                clearTimeout(silenceTimer);
                silenceTimer = null;
            }
            // 停止波形动画
            if (waveformAnimId) {
                cancelAnimationFrame(waveformAnimId);
                waveformAnimId = null;
            }
            document.getElementById('voiceWaveform').style.display = 'none';
            sendAudioForTranscription();
        };
        mediaRecorder.onerror = function() {
            showVoiceToast('录音出错', 'danger');
            cleanupVoiceRecording();
        };
        mediaRecorder.start();
        isVoiceRecording = true;
        btn.classList.add('recording');
        btn.innerHTML = '<i class="fas fa-microphone-alt fa-fade"></i>';
        btn.title = '点击停止录音';
        showVoiceToast('录音中...', 'info');

        // ── 延迟启用静音检测（给用户反应时间） ──
        silenceDetectionEnabled = false;
        if (silenceDetectionTimer) {
            clearTimeout(silenceDetectionTimer);
        }
        silenceDetectionTimer = setTimeout(function() {
            silenceDetectionEnabled = true;
            silenceDetectionTimer = null;
            showVoiceToast('静音检测已启用', 'info');
        }, SILENCE_DETECTION_DELAY_MS);

        // ── 启动静音检测循环（含波形绘制） ──
        startSilenceDetection();

        // ── 启动 60 秒无语音输入超时 ──
        startVoiceIdleTimer();
    } catch (err) {
        console.error('启动录音失败:', err);
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
            showVoiceToast('麦克风权限被拒绝', 'danger');
            showPermissionGuide();
        } else if (err.name === 'NotFoundError') {
            showVoiceToast('未检测到麦克风设备', 'danger');
        } else {
            showVoiceToast('启动录音失败: ' + err.message, 'danger');
        }
    }
}

function startSilenceDetection() {
    if (!analyserNode || !isVoiceRecording) return;

    var dataArray = new Uint8Array(analyserNode.frequencyBinCount);

    function checkSilence() {
        if (!isVoiceRecording || !analyserNode) return;

        analyserNode.getByteTimeDomainData(dataArray);

        // 计算当前音量（RMS）
        var sum = 0;
        for (var i = 0; i < dataArray.length; i++) {
            var value = (dataArray[i] - 128) / 128;
            sum += value * value;
        }
        var rms = Math.sqrt(sum / dataArray.length);

        // ── 绘制实时波形 ──
        drawWaveform(dataArray);

        if (silenceDetectionEnabled) {
            if (rms < SILENCE_THRESHOLD) {
                // 静音中，如果还没有定时器则启动
                if (!silenceTimer) {
                    silenceTimer = setTimeout(function() {
                        // 静音超时，自动停止录音
                        if (isVoiceRecording) {
                            showVoiceToast('检测到静音，自动发送...', 'info');
                            stopVoiceRecording();
                        }
                    }, SILENCE_TIMEOUT_MS);
                }
            } else {
                // 有声音，清除静音定时器
                if (silenceTimer) {
                    clearTimeout(silenceTimer);
                    silenceTimer = null;
                }
                // 有声音输入，重置 idle 超时定时器
                stopVoiceIdleTimer();
                startVoiceIdleTimer();
            }
        }

        // 继续检测
        if (isVoiceRecording) {
            waveformAnimId = requestAnimationFrame(checkSilence);
        }
    }

    checkSilence();
}

// ── 绘制音频波形 ──
function drawWaveform(dataArray) {
    if (!waveformCtx || !waveformCanvas) return;
    var width = waveformCanvas.width;
    var height = waveformCanvas.height;
    waveformCtx.clearRect(0, 0, width, height);

    // 渐变填充
    var gradient = waveformCtx.createLinearGradient(0, 0, width, 0);
    gradient.addColorStop(0, '#6366f1');
    gradient.addColorStop(0.5, '#8b5cf6');
    gradient.addColorStop(1, '#a78bfa');
    waveformCtx.strokeStyle = gradient;
    waveformCtx.lineWidth = 2;

    var sliceWidth = width / dataArray.length;
    var x = 0;
    waveformCtx.beginPath();
    for (var i = 0; i < dataArray.length; i++) {
        var v = dataArray[i] / 128.0;
        var y = (v * height) / 2;
        if (i === 0) {
            waveformCtx.moveTo(x, y);
        } else {
            waveformCtx.lineTo(x, y);
        }
        x += sliceWidth;
    }
    waveformCtx.lineTo(width, height / 2);
    waveformCtx.stroke();
}

function stopVoiceRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
    setVoiceButtonIdle();
}

function startVoiceIdleTimer() {
    stopVoiceIdleTimer(); // 清除之前的定时器
    voiceIdleTimer = setTimeout(function() {
        // 60 秒无语音输入，关闭录音并语音提示
        if (isVoiceRecording) {
            showVoiceToast('60秒无语音输入，已退出语音模式', 'warning');
            // 先停止录音
            if (mediaRecorder && mediaRecorder.state !== 'inactive') {
                mediaRecorder.stop();
            }
            setVoiceButtonIdle();
            // 语音提示 "我先退下了，有需要再叫我"
            if (window.ttsEnabled) {
                var leaveMsg = '我先退下了，有需要再叫我';
                fetch(window.CHAT_URLS.text_to_speech_route, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
                    body: JSON.stringify({
                        text: leaveMsg,
                        voice: window.ttsVoiceName,
                        rate: ttsRate
                    })
                })
                .then(function(r) { return r.blob(); })
                .then(function(blob) {
                    var url = URL.createObjectURL(blob);
                    var player = new Audio(url);
                    player.onended = function() { URL.revokeObjectURL(url); };
                    player.play().catch(function(){});
                })
                .catch(function(){});
            }
        }
    }, VOICE_IDLE_TIMEOUT_MS);
}

function stopVoiceIdleTimer() {
    if (voiceIdleTimer) {
        clearTimeout(voiceIdleTimer);
        voiceIdleTimer = null;
    }
}

function cleanupVoiceRecording() {
    if (audioStream) {
        audioStream.getTracks().forEach(function(t) { t.stop(); });
        audioStream = null;
    }
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }
    analyserNode = null;
    mediaRecorder = null;
    audioChunks = [];
    if (silenceTimer) {
        clearTimeout(silenceTimer);
        silenceTimer = null;
    }
    stopVoiceIdleTimer();
    if (waveformAnimId) {
        cancelAnimationFrame(waveformAnimId);
        waveformAnimId = null;
    }
    document.getElementById('voiceWaveform').style.display = 'none';
    setVoiceButtonIdle();
}

function setVoiceButtonIdle() {
    isVoiceRecording = false;
    const btn = document.getElementById('voiceInputBtn');
    if (btn) {
        btn.classList.remove('recording');
        btn.innerHTML = '<i class="fas fa-microphone"></i>';
        btn.title = '语音输入';
    }
}

function getSupportedMimeType() {
    var types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4', 'audio/wav'];
    for (var i = 0; i < types.length; i++) {
        if (MediaRecorder.isTypeSupported(types[i])) return types[i];
    }
    return null;
}

async function sendAudioForTranscription() {
    if (audioChunks.length === 0) {
        showVoiceToast('未录制到音频', 'warning');
        return;
    }
    showVoiceToast('正在识别语音...', 'info');
    var blob = new Blob(audioChunks, { type: getSupportedMimeType() || 'audio/webm' });
    var formData = new FormData();
    formData.append('audio', blob, 'recording.webm');
    try {
        var response = await fetch(window.CHAT_URLS.speech_to_text, {
            method: 'POST',
            headers: {'X-CSRFToken': getCSRFToken()},
            body: formData,
        });
        var data = await response.json();
        if (data.text) {
            var textarea = document.getElementById('messageInput');
            if (textarea) {
                var start = textarea.selectionStart;
                var end = textarea.selectionEnd;
                var before = textarea.value.substring(0, start);
                var after = textarea.value.substring(end);
                textarea.value = before + data.text + after;
                textarea.selectionStart = textarea.selectionEnd = start + data.text.length;
                textarea.style.height = 'auto';
                textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
                textarea.focus();
            }
            showVoiceToast('语音识别完成', 'success');

            // ── 自动发送：识别成功后自动发送消息 ──
            if (isAutoVoiceMode || document.activeElement === textarea) {
                setTimeout(function() {
                    var form = document.getElementById('chatForm');
                    if (form) {
                        form.dispatchEvent(new Event('submit'));
                    }
                }, 300);
            }
        } else if (data.error) {
            showVoiceToast('识别失败: ' + data.error, 'danger');
        }
    } catch (err) {
        console.error('语音识别请求失败:', err);
        showVoiceToast('语音识别服务请求失败', 'danger');
    } finally {
        audioChunks = [];
    }
}

function showVoiceToast(message, type) {
    var old = document.getElementById('voiceToast');
    if (old) old.remove();

    var toast = document.createElement('div');
    toast.id = 'voiceToast';
    toast.className = 'voice-toast voice-toast-' + type;
    toast.textContent = message;
    var inputArea = document.querySelector('.chat-input-area');
    if (inputArea) inputArea.appendChild(toast);

    setTimeout(function() {
        if (toast.parentNode) toast.remove();
    }, 3000);
}

function showPermissionGuide() {
    var old = document.getElementById('permissionGuide');
    if (old) old.remove();

    var guide = document.createElement('div');
    guide.id = 'permissionGuide';
    guide.className = 'permission-guide';
    guide.innerHTML =
        '<div class="permission-guide-content">' +
            '<button class="permission-guide-close" onclick="this.parentElement.parentElement.remove()">&times;</button>' +
            '<h5><i class="fas fa-microphone-slash"></i> 麦克风权限被拒绝</h5>' +
            '<p>语音输入需要麦克风权限。请按以下步骤操作：</p>' +
            '<ol>' +
                '<li>点击浏览器地址栏左侧的 <strong>🔒 锁图标</strong> 或 <strong>⚠️ 图标</strong></li>' +
                '<li>找到 <strong>麦克风</strong> 权限设置</li>' +
                '<li>将权限改为 <strong>允许</strong></li>' +
                '<li>刷新页面后重试</li>' +
            '</ol>' +
            '<p class="permission-guide-note">💡 提示：语音输入需要麦克风权限才能使用。</p>' +
            '<button class="btn btn-sm btn-primary" onclick="this.closest(\'.permission-guide\').remove()">我知道了</button>' +
        '</div>';
    var inputArea = document.querySelector('.chat-input-area');
    if (inputArea) inputArea.appendChild(guide);
}

// ── 语音设置面板 ──
function toggleVoiceSettings() {
    var panel = document.getElementById('voiceSettingsPanel');
    if (panel) {
        panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    }
}

function updateSilenceThreshold(value) {
    SILENCE_THRESHOLD = parseFloat(value);
}

// ── 语调滑动条 ──
function updatePitchLabel(value) {
    var numVal = parseInt(value);
    ttsPitch = (numVal >= 0 ? '+' : '') + numVal + 'Hz';
    var label = document.getElementById('ttsPitchLabel');
    if (!label) return;
    if (numVal === 0) {
        label.textContent = '正常';
    } else if (numVal > 0) {
        label.textContent = '+' + numVal + 'Hz 较高';
    } else {
        label.textContent = numVal + 'Hz 较低';
    }
}

// ── 加载 TTS 语音列表 ──
document.addEventListener('DOMContentLoaded', function() {
    fetch(window.CHAT_URLS.tts_voices)
    .then(function(r) { return r.json(); })
    .then(function(data) {
        var select = document.getElementById('ttsVoiceSelect');
        if (!select) return;
        var voices = data.voices || {};
        var firstKey = null;
        for (var key in voices) {
            if (!firstKey) firstKey = key;
            var opt = document.createElement('option');
            opt.value = key;
            opt.textContent = voices[key];
            if (key === window.ttsVoiceName) opt.selected = true;
            select.appendChild(opt);
        }
    })
    .catch(function(){});
});

// ── 加载 TTS 音色（说话风格）列表 ──
document.addEventListener('DOMContentLoaded', function() {
    fetch(window.CHAT_URLS.tts_styles)
    .then(function(r) { return r.json(); })
    .then(function(data) {
        var select = document.getElementById('ttsStyleSelect');
        if (!select) return;
        var styles = data.styles || {};
        select.innerHTML = '';
        for (var key in styles) {
            var opt = document.createElement('option');
            opt.value = key;
            opt.textContent = styles[key];
            if (key === ttsStyle) opt.selected = true;
            select.appendChild(opt);
        }
    })
    .catch(function(){});
});

// ── 测试语音：用当前设置试听 ──
function testTTS() {
    var testText = '你好，我是您的智能助手。欢迎使用语音对话功能。';
    fetch(window.CHAT_URLS.text_to_speech_route, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
        body: JSON.stringify({
            text: testText,
            voice: window.ttsVoiceName,
            rate: ttsRate,
            pitch: ttsPitch,
            style: ttsStyle
        })
    })
    .then(function(r) {
        if (!r.ok) throw new Error('TTS 请求失败');
        return r.blob();
    })
    .then(function(blob) {
        var url = URL.createObjectURL(blob);
        var player = new Audio(url);
        player.onended = function() { URL.revokeObjectURL(url); };
        player.play().catch(function(err) {
            console.error('测试语音播放失败:', err);
            showVoiceToast('测试语音播放失败', 'danger');
        });
        showVoiceToast('正在播放测试语音...', 'info');
    })
    .catch(function(err) {
        console.error('测试语音请求失败:', err);
        showVoiceToast('测试语音请求失败: ' + err.message, 'danger');
    });
}

// ═══════════════════════════════════════════════════════════════
// 语音播报 (Text-to-Speech) — 后端 Edge TTS + 打断 + 错误恢复
// ═══════════════════════════════════════════════════════════════
let ttsEnabled = false;  // 默认关闭
let ttsAudioPlayer = null;  // 用于播放后端返回的音频
let ttsVoiceName = 'zh-CN-XiaoxiaoNeural';  // 默认语音
let ttsRetryCount = 0;      // TTS 重试次数
const TTS_MAX_RETRIES = 1;  // 最大重试次数

function toggleTTS() {
    const btn = document.getElementById('ttsToggleBtn');
    ttsEnabled = !ttsEnabled;
    window.ttsEnabled = ttsEnabled;
    if (btn) {
        if (ttsEnabled) {
            btn.classList.add('active');
            btn.innerHTML = '<i class="fas fa-volume-up"></i>';
            btn.title = '语音播报已开启';
            showVoiceToast('语音播报已开启', 'success');
            document.getElementById('voiceSettingsBtn').style.display = '';
        } else {
            btn.classList.remove('active');
            btn.innerHTML = '<i class="fas fa-volume-up"></i>';
            btn.title = '语音播报已关闭';
            ttsAborted = true;
            if (ttsStreamAbortController) {
                ttsStreamAbortController.abort();
                ttsStreamAbortController = null;
            }
            if (ttsAudioPlayer) {
                ttsAudioPlayer.pause();
                ttsAudioPlayer.src = '';
                ttsAudioPlayer = null;
            }
            if (ttsMediaSource) {
                try { ttsMediaSource.endOfStream(); } catch(e) {}
                ttsMediaSource = null;
            }
            ttsSourceBuffer = null;
            document.getElementById('voiceSettingsBtn').style.display = 'none';
            document.getElementById('voiceSettingsPanel').style.display = 'none';
            showVoiceToast('语音播报已关闭', 'info');
        }
    }
}

// ── SSE 流式 TTS（MediaSource 边下载边播放） ──
let ttsAborted = false;
let ttsMediaSource = null;
let ttsSourceBuffer = null;
let ttsStreamAbortController = null;
let ttsBufferQueue = [];
let ttsBufferAppending = false;

function speakText(text) {
    if (!window.ttsEnabled) return;

    const plainText = stripMarkdown(text);
    if (!plainText.trim()) return;

    ttsAborted = true;
    if (ttsStreamAbortController) {
        ttsStreamAbortController.abort();
        ttsStreamAbortController = null;
    }
    if (ttsAudioPlayer) {
        ttsAudioPlayer.pause();
        ttsAudioPlayer.src = '';
        ttsAudioPlayer = null;
    }
    if (ttsMediaSource) {
        try { ttsMediaSource.endOfStream(); } catch(e) {}
        ttsMediaSource = null;
    }
    ttsSourceBuffer = null;

    ttsAborted = false;
    ttsRetryCount = 0;

    if (!window.MediaSource) {
        console.warn('MediaSource 不支持，降级到非流式 TTS');
        fallbackTTS(plainText);
        return;
    }

    ttsMediaSource = new MediaSource();
    var audioUrl = URL.createObjectURL(ttsMediaSource);
    ttsAudioPlayer = new Audio(audioUrl);

    ttsAudioPlayer.onended = function() {
        URL.revokeObjectURL(audioUrl);
        ttsAudioPlayer = null;
        ttsMediaSource = null;
        ttsSourceBuffer = null;
        if (window.ttsEnabled && !isVoiceRecording && !isStreaming && !ttsAborted) {
            setTimeout(function() {
                startVoiceRecording();
            }, 500);
        }
    };

    ttsAudioPlayer.onerror = function() {
        console.error('TTS 流式播放失败');
        URL.revokeObjectURL(audioUrl);
        ttsAudioPlayer = null;
        ttsMediaSource = null;
        ttsSourceBuffer = null;
        if (!ttsAborted) {
            fallbackTTS(plainText);
        }
    };

    ttsMediaSource.addEventListener('sourceopen', function() {
        if (ttsAborted) return;

        try {
            ttsSourceBuffer = ttsMediaSource.addSourceBuffer('audio/mpeg');
        } catch(e) {
            console.error('添加 SourceBuffer 失败:', e);
            fallbackTTS(plainText);
            return;
        }

        ttsSourceBuffer.addEventListener('updateend', function() {
            ttsBufferAppending = false;
            processBufferQueue();
        });

        ttsStreamAbortController = new AbortController();
        var signal = ttsStreamAbortController.signal;

        fetch(window.CHAT_URLS.text_to_speech_stream_route, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
            body: JSON.stringify({
                text: plainText,
                voice: window.ttsVoiceName,
                rate: ttsRate,
                pitch: ttsPitch,
                style: ttsStyle
            }),
            signal: signal
        })
        .then(function(response) {
            if (!response.ok) {
                throw new Error('TTS 流式请求失败: ' + response.status);
            }
            return response.body.getReader();
        })
        .then(function(reader) {
            var decoder = new TextDecoder();
            var buffer = '';
            var chunksReceived = 0;

            function readChunk() {
                if (ttsAborted) {
                    reader.cancel();
                    return;
                }

                reader.read().then(function(result) {
                    if (result.done) {
                        if (!ttsAborted && ttsMediaSource && ttsMediaSource.readyState === 'open') {
                            try {
                                ttsMediaSource.endOfStream();
                            } catch(e) {}
                        }
                        return;
                    }

                    buffer += decoder.decode(result.value, {stream: true});
                    var lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (var i = 0; i < lines.length; i++) {
                        var line = lines[i];
                        if (line.startsWith('data: ')) {
                            try {
                                var data = JSON.parse(line.slice(6));
                                if (data.type === 'audio_chunk' && data.data) {
                                    chunksReceived++;
                                    var binaryStr = atob(data.data);
                                    var byteArray = new Uint8Array(binaryStr.length);
                                    for (var j = 0; j < binaryStr.length; j++) {
                                        byteArray[j] = binaryStr.charCodeAt(j);
                                    }
                                    if (ttsSourceBuffer && !ttsAborted) {
                                        ttsBufferQueue.push(byteArray.buffer);
                                        processBufferQueue();
                                    }
                                } else if (data.type === 'done') {
                                    console.log('TTS 流式合成完成，共 ' + chunksReceived + ' 个 chunk');
                                    if (!ttsAborted && ttsMediaSource && ttsMediaSource.readyState === 'open') {
                                        try {
                                            ttsMediaSource.endOfStream();
                                        } catch(e) {}
                                    }
                                } else if (data.type === 'error') {
                                    console.error('TTS 流式错误:', data.message);
                                    if (!ttsAborted) {
                                        fallbackTTS(plainText);
                                    }
                                }
                            } catch(e) {
                                console.warn('解析 SSE 数据失败:', e);
                            }
                        }
                    }

                    readChunk();
                }).catch(function(err) {
                    if (err.name !== 'AbortError') {
                        console.error('读取 TTS 流失败:', err);
                        if (!ttsAborted) {
                            fallbackTTS(plainText);
                        }
                    }
                });
            }

            readChunk();
        })
        .catch(function(err) {
            if (err.name !== 'AbortError') {
                console.error('TTS 流式请求失败:', err);
                if (!ttsAborted) {
                    fallbackTTS(plainText);
                }
            }
        });
    });

    function processBufferQueue() {
        if (ttsAborted || !ttsSourceBuffer || ttsBufferAppending) return;
        if (ttsBufferQueue.length === 0) return;

        ttsBufferAppending = true;
        var chunk = ttsBufferQueue.shift();
        try {
            ttsSourceBuffer.appendBuffer(chunk);
        } catch(e) {
            console.warn('SourceBuffer 追加失败:', e);
            ttsBufferAppending = false;
            processBufferQueue();
        }
    }

    ttsAudioPlayer.play().catch(function(err) {
        console.error('TTS 播放启动失败:', err);
        if (!ttsAborted) {
            fallbackTTS(plainText);
        }
    });
}

// ── 降级方案：非流式 TTS ──
function fallbackTTS(text) {
    if (ttsAborted || !text) return;

    fetch(window.CHAT_URLS.text_to_speech_route, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
        body: JSON.stringify({
            text: text,
            voice: window.ttsVoiceName,
            rate: ttsRate,
            pitch: ttsPitch,
            style: ttsStyle
        })
    })
    .then(function(response) {
        if (!response.ok) throw new Error('TTS 请求失败: ' + response.status);
        return response.blob();
    })
    .then(function(audioBlob) {
        if (ttsAborted) return;
        var audioUrl = URL.createObjectURL(audioBlob);
        ttsAudioPlayer = new Audio(audioUrl);
        ttsAudioPlayer.onended = function() {
            URL.revokeObjectURL(audioUrl);
            ttsAudioPlayer = null;
            if (window.ttsEnabled && !isVoiceRecording && !isStreaming && !ttsAborted) {
                setTimeout(function() { startVoiceRecording(); }, 500);
            }
        };
        ttsAudioPlayer.onerror = function() {
            URL.revokeObjectURL(audioUrl);
            ttsAudioPlayer = null;
            if ('speechSynthesis' in window && !ttsAborted) {
                var utterance = new SpeechSynthesisUtterance(text);
                utterance.lang = 'zh-CN';
                utterance.rate = 1.0;
                utterance.onend = function() {
                    if (window.ttsEnabled && !isVoiceRecording && !isStreaming && !ttsAborted) {
                        setTimeout(function() { startVoiceRecording(); }, 500);
                    }
                };
                speechSynthesis.speak(utterance);
            }
        };
        ttsAudioPlayer.play().catch(function(err) {
            console.error('降级 TTS 播放失败:', err);
        });
    })
    .catch(function(err) {
        console.error('降级 TTS 请求失败:', err);
        if ('speechSynthesis' in window && !ttsAborted) {
            var utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = 'zh-CN';
            utterance.rate = 1.0;
            speechSynthesis.speak(utterance);
        }
    });
}

// ── 语音打断 ──
function setupVoiceInterrupt() {
    var interruptCheck = setInterval(function() {
        if (ttsAudioPlayer && !ttsAudioPlayer.paused && isVoiceRecording) {
            console.log('语音打断：检测到用户说话，停止 TTS 播报');
            ttsAudioPlayer.pause();
            ttsAudioPlayer = null;
            showVoiceToast('已打断语音播报', 'info');
        }
    }, 500);
    window._voiceInterruptInterval = interruptCheck;
}

document.addEventListener('DOMContentLoaded', function() {
    setupVoiceInterrupt();
});

function stripMarkdown(text) {
    if (!text) return '';
    return text
        .replace(/```[\s\S]*?```/g, '代码块')
        .replace(/`([^`]+)`/g, '$1')
        .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
        .replace(/[*_~#>`]/g, '')
        .replace(/\n{2,}/g, '\n')
        .replace(/^\s*[-*+]\s+/gm, '')
        .replace(/^\s*\d+\.\s+/gm, '')
        .replace(/\|/g, '')
        .replace(/[\u{1F000}-\u{1FFFF}]/gu, '')
        .replace(/[\u{2000}-\u{27BF}]/gu, '')
        .replace(/[\u{2900}-\u{2BFF}]/gu, '')
        .replace(/[\u{FE00}-\u{FE0F}]/gu, '')
        .replace(/[\u{200D}]/gu, '')
        .replace(/[\u{2300}-\u{23FF}]/gu, '')
        .replace(/[\u{25A0}-\u{25FF}]/gu, '')
        .replace(/[\u{2600}-\u{26FF}]/gu, '')
        .replace(/[\u{2700}-\u{27BF}]/gu, '')
        .replace(/[\u{2B50}]/gu, '')
        .replace(/[\u{2934}-\u{2935}]/gu, '')
        .replace(/[\u{3030}]/gu, '')
        .replace(/[\u{303D}]/gu, '')
        .replace(/[\u{3297}]/gu, '')
        .replace(/[\u{3299}]/gu, '')
        .replace(/[\u{1F600}-\u{1F64F}]/gu, '')
        .replace(/[\u{1F300}-\u{1F5FF}]/gu, '')
        .replace(/[\u{1F680}-\u{1F6FF}]/gu, '')
        .replace(/[\u{1F900}-\u{1F9FF}]/gu, '')
        .replace(/[\u{1FA00}-\u{1FA6F}]/gu, '')
        .replace(/[\u{1FA70}-\u{1FAFF}]/gu, '')
        .replace(/[\u{260E}]/gu, '')
        .replace(/[\u{2611}]/gu, '')
        .replace(/[\u{2614}]/gu, '')
        .replace(/[\u{2615}]/gu, '')
        .replace(/[\u{2640}]/gu, '')
        .replace(/[\u{2642}]/gu, '')
        .replace(/[\u{2660}]/gu, '')
        .replace(/[\u{2663}]/gu, '')
        .replace(/[\u{2665}]/gu, '')
        .replace(/[\u{2666}]/gu, '')
        .replace(/[\u{2668}]/gu, '')
        .replace(/[\u{267B}]/gu, '')
        .replace(/[\u{267F}]/gu, '')
        .replace(/[\u{2693}]/gu, '')
        .replace(/[\u{26A0}]/gu, '')
        .replace(/[\u{26A1}]/gu, '')
        .replace(/[\u{26BD}]/gu, '')
        .replace(/[\u{26BE}]/gu, '')
        .replace(/[\u{26C4}]/gu, '')
        .replace(/[\u{26C5}]/gu, '')
        .replace(/[\u{26D4}]/gu, '')
        .replace(/[\u{26EA}]/gu, '')
        .replace(/[\u{26F2}]/gu, '')
        .replace(/[\u{26F3}]/gu, '')
        .replace(/[\u{26F5}]/gu, '')
        .replace(/[\u{26FA}]/gu, '')
        .replace(/[\u{26FD}]/gu, '')
        .replace(/[\u{2702}]/gu, '')
        .replace(/[\u{2708}]/gu, '')
        .replace(/[\u{2709}]/gu, '')
        .replace(/[\u{270A}]/gu, '')
        .replace(/[\u{270B}]/gu, '')
        .replace(/[\u{270C}]/gu, '')
        .replace(/[\u{270F}]/gu, '')
        .replace(/[\u{2712}]/gu, '')
        .replace(/[\u{2714}]/gu, '')
        .replace(/[\u{2716}]/gu, '')
        .replace(/[\u{2728}]/gu, '')
        .replace(/[\u{2733}]/gu, '')
        .replace(/[\u{2734}]/gu, '')
        .replace(/[\u{2744}]/gu, '')
        .replace(/[\u{2747}]/gu, '')
        .replace(/[\u{274C}]/gu, '')
        .replace(/[\u{274E}]/gu, '')
        .replace(/[\u{2753}]/gu, '')
        .replace(/[\u{2754}]/gu, '')
        .replace(/[\u{2755}]/gu, '')
        .replace(/[\u{2757}]/gu, '')
        .replace(/[\u{2764}]/gu, '')
        .replace(/[\u{2795}]/gu, '')
        .replace(/[\u{2796}]/gu, '')
        .replace(/[\u{2797}]/gu, '')
        .replace(/[\u{27A1}]/gu, '')
        .replace(/[\u{27B0}]/gu, '')
        .replace(/[\u{27BF}]/gu, '')
        .replace(/[\u{2934}]/gu, '')
        .replace(/[\u{2935}]/gu, '')
        .replace(/[\u{2B05}]/gu, '')
        .replace(/[\u{2B06}]/gu, '')
        .replace(/[\u{2B07}]/gu, '')
        .replace(/[\u{2B1B}]/gu, '')
        .replace(/[\u{2B1C}]/gu, '')
        .replace(/[\u{2B50}]/gu, '')
        .replace(/[\u{2B55}]/gu, '')
        .replace(/[\u{3030}]/gu, '')
        .replace(/[\u{303D}]/gu, '')
        .replace(/[\u{3297}]/gu, '')
        .replace(/[\u{3299}]/gu, '')
        .replace(/[🇦-🇿]/gu, '')
        .replace(/[*_~#>`\\]/g, '')
        .replace(/\*{2,}/g, '')
        .replace(/\_{2,}/g, '')
        .trim();
}


