from flask import Flask, request
from flask import render_template
from flask_wtf.csrf import CSRFError
from jinja2 import TemplateNotFound
from werkzeug.exceptions import HTTPException, NotFound


def init_errors(app: Flask):
    @app.errorhandler(400)
    def bad_request(e):
        return render_template('errors/400.html', description=e.description), 400
    
    @app.errorhandler(403)
    def forbidden_request(e):
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            response = jsonify({'error': 'forbidden'})
            response.status_code = 403
            return response
        return render_template('errors/403.html', description=e.description), 403

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html', description=e.description), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html', description=e.description), 500

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        return render_template('errors/400.html', description=e.description), 400
        
    @app.errorhandler(TemplateNotFound)
    def handle_template_not_found_error(e):
        """
        Renders template when a TemplateNotFound exception occurs.
        """
        return render_template('errors/404.html',description=e), 404
     
    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        """
        Returns just the error message for HTTP exceptions.
        """
        return render_template('errors/500.html',description=e), 500
     
    @app.errorhandler(Exception)
    def handle_exception(e):
        """
        Returns a simple string for other exceptions.
        """
        return render_template('errors/500.html',description=e), 500
        
    @app.errorhandler(ModuleNotFoundError)
    def handle_exception(e):
        """
        Returns a simple string for other exceptions.
        """
        return render_template('errors/500.html',description=e), 500
        
        