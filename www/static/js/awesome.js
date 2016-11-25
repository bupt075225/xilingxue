// awesome.js

function showError(err) {
    var alert = $('div.uk-alert-danger');
    if (err) {
        alert.text(err.message || err.error || err).removeClass('uk-hidden').show();
        try {
            if (alert.offset().top < ($(window).scrollTop() - 41)) {
                $('html,body').animate({scrollTop: alert.offset().top - 41});    
            }    
        }
        catch (e) {}
    }
    else {
        alert.addClass('uk-hidden').hide().text('');
    }
}

function _ajax(method, url, data, callback) {
    $.ajax({
        type: method,
        url: url,
        data: data,
        dataType: 'json'
    }).done(function(r) {
        if (r && r.error) {
            return callback && callback(r);    
        }
        return callback && callback(null, r);
    }).fail(function(jqXHR, textStatus) {
        return callback && callback({error: 'HTTP' + jqXHR.status, message: 'Network error (HTTP ' + jqXHR.status + ')'}); 
    });    
}

function getApi(url, data, callback) {
    if (arguments.length === 2) {
        callback = data;
        data = {};
    }    
    _ajax('GET', url, data, callback)
}

function postApi(url, data, callback) {
    if (arguments.length === 2) {
        callback = data;
        data = {};
    }
    _ajax('POST', url, data, callback)
}

function startLoading() {
    var btn = $('form').find('button[type=submit]');
    var icon = btn.find('i');
    icon.addClass('uk-icon-spinner').addClass('uk-icon-spin');
    btn.attr('disabled', 'disabled');
}

function stopLoading() {
    var btn = $('form').find('button[type=submit]');
    var icon = btn.find('i');
    icon.removeClass('uk-icon-spin').removeClass('uk-icon-spinner');
    btn.removeAttr('disabled');
}
