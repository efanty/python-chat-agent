function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 点击页面其它区域时关闭下拉菜单（原生事件，避免 jQuery 冲突）
document.addEventListener('click', function(e) {
    var dd = e.target.closest('.dropdown, [data-toggle="dropdown"]');
    if (!dd) {
        document.querySelectorAll('.dropdown.open').forEach(function(el) {
            el.classList.remove('open');
        });
    }
});

$(document).ready(function () {
    var ENTER_KEY = 13;
    var ESC_KEY = 27;

    // Bootstrap Toast initialization
    var toastElList = [].slice.call(document.querySelectorAll('.toast'));
    var toastList = toastElList.map(function (toastEl) {
        return new bootstrap.Toast(toastEl);
    });

    function showToast(message, type) {
        var container = document.getElementById('toastContainer');
        if (!container) return;
        var bgColor = type === 'error' ? '#dc3545' : '#28a745';
        var icon = type === 'error' ? 'fa-times-circle' : 'fa-check-circle';
        var $toast = $(
            '<div class="toast-notification" style="background:' + bgColor +
            ';color:#fff;padding:10px 16px;border-radius:6px;margin-bottom:8px;' +
            'box-shadow:0 4px 12px rgba(0,0,0,0.15);display:flex;align-items:center;' +
            'font-size:14px;min-width:200px;cursor:pointer">' +
            '<i class="fa ' + icon + '" style="margin-right:8px"></i>' +
            '<span>' + escapeHtml(message) + '</span>' +
            '</div>'
        );
        $toast.appendTo(container).hide().fadeIn(300);
        $toast.on('click', function () { $(this).fadeOut(300, function () { $(this).remove(); }); });
        setTimeout(function () { $toast.fadeOut(300, function () { $toast.remove(); }); }, 3000);
    }

    $(document).ajaxError(function (event, request) {
        var message = null;

        if (request.responseJSON && request.responseJSON.hasOwnProperty('message')) {
            message = request.responseJSON.message;
        } else if (request.responseText) {
            var IS_JSON = true;
            try {
                var data = JSON.parse(request.responseText);
            }
            catch (err) {
                IS_JSON = false;
            }

            if (IS_JSON && data !== undefined && data.hasOwnProperty('message')) {
                message = JSON.parse(request.responseText).message;
            } else {
                message = default_error_message;
            }
        } else {
            message = default_error_message;
        }
        showToast(message, 'error');
    });

    $.ajaxSetup({
        beforeSend: function (xhr, settings) {
            if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type) && !this.crossDomain) {
                xhr.setRequestHeader('X-CSRFToken', csrf_token);
            }
        }
    });

    // Bind a callback that executes when document.location.hash changes.
    $(window).bind('hashchange', function () {
        // Some browsers return the hash symbol, and some don't.
        var hash = window.location.hash.replace('#', '');
        var url = null;
        if (hash === 'login') {
            url = login_page_url;
        } else if (hash === 'app') {
            url = app_page_url;
        } else if (hash === 'password') {
            url = password_url;
        } else if (hash === 'settings') {
            url = settings_url;
        } else if (hash === 'actives') {
            url = actives_url;
        } else if (hash === 'search') {
            url = search_url;
        } else {
            url = actives_url;
        }

        $.ajax({
            type: 'GET',
            url: url,
            success: function (data) {
                $('#main').hide().html(data).fadeIn(800);
                initializeBootstrap();
            }
        });
    });

    // 页面已有完整服务端渲染内容，不再触发 AJAX hashchange 覆盖

    function toggle_password() {
        var password_input = document.getElementById('password-input');
        if (password_input.type === 'password') {
            password_input.type = 'text';
        } else {
            password_input.type = 'password';
        }
    }

    $(document).on('click', '#toggle-password', toggle_password);

    function display_dashboard() {
        var all_count = $('.item').length;
        if (all_count === 0) {
            $('#dashboard').show();
        } else {
            $('#dashboard').show();
            // Bootstrap tabs are already initialized via data attributes
        }
    }

    function initializeBootstrap() {
        // Initialize Bootstrap components if needed
        // Tooltips
        var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
        // Modals
        var modalElList = [].slice.call(document.querySelectorAll('.modal'));
        var modalList = modalElList.map(function (modalEl) {
            return new bootstrap.Modal(modalEl);
        });
        // Dropdowns
        var dropdownElList = [].slice.call(document.querySelectorAll('.dropdown-toggle'));
        var dropdownList = dropdownElList.map(function (dropdownToggleEl) {
            return new bootstrap.Dropdown(dropdownToggleEl);
        });
        display_dashboard();
    }

    function remove_edit_input() {
        var $edit_input = $('#edit-item-input');
        var $input = $('#item-input');
        var $edit_card = $edit_input.closest('.card');

        $edit_card.prev('.item').show();
        $edit_card.remove();
        //$input.focus();
    }

    function refresh_count() {
        var $items = $('.item');

        display_dashboard();
        var all_count = $items.length;
        var active_count = $items.filter(function () {
            return $(this).data('done') === false;
        }).length;
        var completed_count = $items.filter(function () {
            return $(this).data('done') === true;
        }).length;
        var active_items = $('#active-count-nav').data();
        $('#all-count').text(all_count);
        $('#active-count').text(active_count);
        $('#active-count-nav').text(active_items);
        $('#completed-count').text(completed_count);
    }

    function new_item(e) {
        var $input = $('#item-input');
        var value = $input.val().trim();
        if (e.which !== ENTER_KEY || !value) {
            return;
        }
        $input.focus().val('');
        var dueDate = $('#new-due-date').val() || '';
        $('#new-due-date').val('');
        $.ajax({
            type: 'POST',
            url: new_item_url,
            data: JSON.stringify({'body': value, 'due_date': dueDate}),
            contentType: 'application/json;charset=UTF-8',
            success: function (data) {
                showToast(data.message, 'success');
                $('.items').append(data.html);
                initializeBootstrap();
                refresh_count();
            }
        });
    }

    function change_date(e) {
        var $timestamp = $('#timestamp');
        var value = $timestamp.val();
        
        // 先 POST 保存日期到 session，再跳转到 ?date= 以避免 cookie 时序问题
        $.ajax({
            type: 'POST',
            url: app_page_url,
            data: JSON.stringify({'search-item-timestamp': value}),
            contentType: 'application/json;charset=UTF-8',
            success: function () {
                window.location.href = app_page_url + '?date=' + encodeURIComponent(value);
            },
            error: function () {
                window.location.href = app_page_url + '?date=' + encodeURIComponent(value);
            }
        });
    }
    
    function edit_item(e) {
        var $edit_input = $('#edit-item-input');
        var value = $edit_input.val().trim();
        if (e.which !== ENTER_KEY || !value) {
            return;
        }
        $edit_input.val('');

        if (!value) {
            showToast(empty_body_error_message, 'error');
            return;
        }

        // .item 是编辑卡的前一个兄弟元素
        var $item = $edit_input.closest('.card').prev('.item');
        var url = $item.data('href');
        var id = $item.data('id');
        var dueDate = $('#edit-due-date').val() || '';

        $.ajax({
            type: 'PUT',
            url: url,
            data: JSON.stringify({'body': value, 'due_date': dueDate}),
            contentType: 'application/json;charset=UTF-8',
            success: function (data) {
                $('#body' + id).text(value);
                $item.data('body', value);
                $item.data('due-date', dueDate);

                // 立即更新截止日期 badge，无需刷新页面
                var $itemBody = $item.find('.item-body');
                var $badge = $itemBody.find('.badge');
                if (dueDate) {
                    // 确定颜色：过期且未完成 → bg-danger，否则 bg-primary
                    var today = new Date();
                    var todayStr = today.getFullYear() + '-' +
                        ('0' + (today.getMonth() + 1)).slice(-2) + '-' +
                        ('0' + today.getDate()).slice(-2);
                    var isOverdue = dueDate < todayStr && !$item.data('done');
                    var badgeClass = isOverdue ? 'bg-danger' : 'bg-primary';
                    var badgeText = '截止: ' + dueDate;
                    if ($badge.length) {
                        $badge.text(badgeText).removeClass('bg-danger bg-primary').addClass(badgeClass);
                    } else {
                        $itemBody.append('<span class="badge ' + badgeClass + '">' + badgeText + '</span>');
                    }
                } else {
                    // 清空截止日期 → 移除 badge
                    if ($badge.length) $badge.remove();
                }

                remove_edit_input();
                showToast(data.message, 'success');
            }
        });
    }

    // add new item
    $(document).on('keyup', '#item-input', new_item.bind(this));
    
    // change date
    $(document).on('keyup', '#timestamp', change_date.bind(this));

    // edit item
    $(document).on('keyup', '#edit-item-input', edit_item.bind(this));
    
    $(document).on('change', '#timestamp', change_date);

    $(document).on('click', '.done-btn', function () {
        var $input = $('#item-input');
        var $item = $(this).closest('.item');
        var $this = $(this);

        if ($item.data('done')) {
            $.ajax({
                type: 'PATCH',
                url: $this.data('href'),
                success: function (data) {
                    $this.find('i').toggleClass('fa-square fa-check-square');
                    $item.find('.item-body span').toggleClass('text-muted text-decoration-line-through text-dark');
                    $item.data('done', false);
                    showToast(data.message, 'success');
                    refresh_count();
                }
            });
        } else {
            $.ajax({
                type: 'PATCH',
                url: $this.data('href'),
                success: function (data) {
                    $this.find('i').toggleClass('fa-square fa-check-square');
                    $item.find('.item-body span').toggleClass('text-dark text-muted text-decoration-line-through');
                    $item.data('done', true);
                    showToast(data.message, 'success');
                    refresh_count();
                }
            });
        }
    });

    // hide and show edit buttons
    $(document).on('mouseenter', '.item', function () {
        $(this).find('.edit-btns').removeClass('d-none');
    }).on('mouseleave', '.item', function () {
        $(this).find('.edit-btns').addClass('d-none');
    });

    // edit item
    $(document).on('click', '.edit-btn', function () {
        var $item = $(this).closest('.item');
        var itemId = $item.data('id');
        var itemBody = $('#body' + itemId).text();
        var dueDate = $item.data('due-date') || '';
        $item.hide();
        $item.after('<div class="card shadow-sm mb-2">' +
                    '<div class="card-body">' +
                    '<div class="input-group mb-2">' +
                    '<input class="form-control" id="edit-item-input" type="text" value="' + itemBody + '" autocomplete="off" required>' +
                    '</div>' +
                    '<div class="input-group">' +
                    '<span class="input-group-text">截止</span>' +
                    '<input class="form-control" id="edit-due-date" type="date" value="' + dueDate + '">' +
                    '</div>' +
                    '</div></div>');

        var $edit_input = $('#edit-item-input');
        var strLength = $edit_input.val().length * 2;
        $edit_input.focus();
        $edit_input[0].setSelectionRange(strLength, strLength);

        $(document).on('keydown', function (e) {
            if (e.keyCode === ESC_KEY) {
                remove_edit_input();
            }
        });

        // 点击编辑卡片以外的区域才关闭编辑，允许点击截止日期输入框
        $(document).on('focusout', '#edit-item-input', function (e) {
            var $editCard = $(this).closest('.card');
            // relatedTarget 为 null 时（点击非焦点元素）延迟检查
            setTimeout(function () {
                if (!$editCard.find(':focus').length) {
                    remove_edit_input();
                }
            }, 120);
        });
    });

    $(document).on('click', '.delete-btn', function () {
        var $input = $('#item-input');
        var $item = $(this).closest('.item');

        $.ajax({
            type: 'DELETE',
            url: $(this).data('href'),
            success: function (data) {
                $item.remove();
                initializeBootstrap();
                refresh_count();
                showToast(data.message, 'success');
            }
        });
    });

    function del_user() {
        var user_id = $(this).data('href');
        var data = {'user_id': user_id};
        if (confirm("Are you sure?")) {
            $.ajax({
                type: 'POST',
                url: settings_url,
                data: JSON.stringify(data),
                contentType: 'application/json;charset=UTF-8',
                success: function (data) {
                    if (window.location.hash === '#settings' || window.location.hash === 'settings') {
                        $(window).trigger('hashchange');
                    } else {
                        window.location.hash = '#settings';
                    }
                    showToast(data.message, 'success');
                }
            });
        }
    }
    
    $(document).on('click', '.del-user-btn', del_user);

    function register() {
        var username = $('#username-input').val();
        var password = $('#password-input').val();
        if (!username || !password) {
            showToast(login_error_message, 'error');
            return;
        }
        var data = {'username': username, 'password': password};
        $.ajax({
            type: 'POST',
            url: register_url,
            data: JSON.stringify(data),
            contentType: 'application/json;charset=UTF-8',
            success: function (data) {
                showToast(data.message, 'success');
            }
        });
    }

    $(document).on('click', '#register-btn', register);

    function search(e) {
        var value = $("#search-input").val();
        if (e.which !== ENTER_KEY || !value) {
            return;
        }
        if (!value) {
            showToast(empty_body_error_message, 'error');
            return;
        }
        $.ajax({
            type: 'POST',
            url: search_url,
            data: JSON.stringify({'body': value}),
            contentType: 'application/json;charset=UTF-8',
            success: function (data) {
                if (window.location.hash === '#search' || window.location.hash === 'search') {
                    $(window).trigger('hashchange');
                } else {
                    window.location.hash = '#search';
                }
                initializeBootstrap();
                showToast(data.message, 'success');
            }
        });
    }

    $(document).on('keyup', '#search-input', search.bind(this));
    $(document).on('click', '#search-btn-close', search);

    function login_user() {
        var username = $('#username-input').val();
        var password = $('#password-input').val();
        if (!username || !password) {
            showToast(login_error_message, 'error');
            return;
        }
        var data = {'username': username, 'password': password};
        $.ajax({
            type: 'POST',
            url: login_url,
            data: JSON.stringify(data),
            contentType: 'application/json;charset=UTF-8',
            success: function (data) {
                if (window.location.hash === '#app' || window.location.hash === 'app') {
                    $(window).trigger('hashchange');
                } else {
                    window.location.hash = '#app';
                }
                initializeBootstrap();
                showToast(data.message, 'success');
            }
        });
    }

    $(document).on('keyup', '.login-input', function (e) {
        if (e.which === ENTER_KEY) {
            login_user();
        }
    });

    $(document).on('click', '#login-btn', login_user);

    $(document).on('click', '#logout-btn', function () {
        $.ajax({
            type: 'GET',
            url: logout_url,
            success: function (data) {
                window.location.hash = '#intro';
                initializeBootstrap();
                showToast(data.message, 'success');
            }
        });
    });

    function reset_password() {
        var password = $('#password-input').val();
        var password2 = $('#password-input2').val();
        if (!password || !password2) {
            showToast(login_error_message, 'error');
            return;
        }
        if (password2 !== password) {
            showToast("Two passwords are not same!", 'error');
            return;
        }
        var data = {'password': password};
        $.ajax({
            type: 'POST',
            url: password_url,
            data: JSON.stringify(data),
            contentType: 'application/json;charset=UTF-8',
            success: function (data) {
                if (window.location.hash === '#app' || window.location.hash === 'app') {
                    $(window).trigger('hashchange');
                } else {
                    window.location.hash = '#app';
                }
                initializeBootstrap();
                showToast("Password has been changed!", 'success');
            }
        });
    }
    
    $(document).on('keyup', '.reset-input', function (e) {
        if (e.which === ENTER_KEY) {
            reset_password();
        }
    });

    $(document).on('click', '#reset-btn', reset_password);

    $(document).on('click', '#active-item', function () {
        var $items = $('.item');
        $items.show();
        $items.filter(function () {
            return $(this).data('done');
        }).hide();
    });

    $(document).on('click', '#completed-item', function () {
        var $input = $('#item-input');
        var $items = $('.item');
        $items.show();
        $items.filter(function () {
            return !$(this).data('done');
        }).hide();
    });

    $(document).on('click', '#all-item', function () {
        $('.item').show();
    });

    $(document).on('click', '#clear-btn', function () {
        var $input = $('#item-input');
        var $items = $('.item');
        $.ajax({
            type: 'DELETE',
            url: clear_item_url,
            success: function (data) {
                $items.filter(function () {
                    return $(this).data('done');
                }).remove();
                showToast(data.message, 'success');
                refresh_count();
            }
        });
    });

    $(document).on('click', '.lang-btn', function () {
        $.ajax({
            type: 'GET',
            url: $(this).data('href'),
            success: function (data) {
                $(window).trigger('hashchange');
                initializeBootstrap();
                showToast(data.message, 'success');
            }
        });
    });

    initializeBootstrap(); // initialize Bootstrap components
});
