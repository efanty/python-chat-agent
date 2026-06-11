// DeepAgent Chat - Main JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Sidebar toggle (mobile + desktop)
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                // Mobile: slide-in overlay behavior
                sidebar.classList.toggle('open');
                if (sidebarOverlay) sidebarOverlay.classList.toggle('open');
            } else {
                // Desktop: smooth collapse/expand
                sidebar.classList.toggle('collapsed');
            }
        });
        if (sidebarOverlay) {
            sidebarOverlay.addEventListener('click', () => {
                sidebar.classList.remove('open');
                sidebarOverlay.classList.remove('open');
            });
        }
    }

    // Admin mobile sidebar toggle
    const adminToggle = document.getElementById('adminSidebarToggle');
    const adminSidebar = document.getElementById('adminSidebar');
    const adminOverlay = document.getElementById('adminOverlay');
    if (adminToggle && adminSidebar) {
        adminToggle.addEventListener('click', () => {
            adminSidebar.classList.toggle('open');
            if (adminOverlay) adminOverlay.classList.toggle('open');
        });
        if (adminOverlay) {
            adminOverlay.addEventListener('click', () => {
                adminSidebar.classList.remove('open');
                adminOverlay.classList.remove('open');
            });
        }
    }

    // Auto-resize textarea
    const textarea = document.getElementById('messageInput');
    if (textarea) {
        textarea.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 150) + 'px';
        });
    }

    // File attachment display
    const fileInput = document.getElementById('fileInput');
    const fileAttach = document.getElementById('fileAttachment');
    if (fileInput && fileAttach) {
        fileInput.addEventListener('change', function() {
            if (this.files && this.files[0]) {
                fileAttach.innerHTML = `<i class="fas fa-paperclip"></i> ${this.files[0].name} <button type="button" class="btn btn-sm text-muted" onclick="clearFile()"><i class="fas fa-times"></i></button>`;
                fileAttach.style.display = 'inline-flex';
            }
        });
    }

    // Auto-scroll to bottom
    const chatMessages = document.getElementById('chatMessages');
    if (chatMessages) {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
});

function clearFile() {
    const fileInput = document.getElementById('fileInput');
    const fileAttach = document.getElementById('fileAttachment');
    if (fileInput) fileInput.value = '';
    if (fileAttach) fileAttach.style.display = 'none';
}

// Toast auto-dismiss
setTimeout(() => {
    document.querySelectorAll('.alert').forEach(el => {
        el.style.transition = 'opacity 0.5s';
        el.style.opacity = '0';
        setTimeout(() => el.remove(), 500);
    });
}, 4000);
