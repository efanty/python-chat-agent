from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, HiddenField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional


class LoginForm(FlaskForm):
    username = StringField("用户名", validators=[DataRequired()])
    password = PasswordField("密码", validators=[DataRequired()])
    remember = BooleanField("记住我")
    submit = SubmitField("登录")


class TOTPForm(FlaskForm):
    code = StringField("TOTP验证码", validators=[DataRequired(), Length(min=6, max=6)])
    submit = SubmitField("验证")


class RegisterForm(FlaskForm):
    username = StringField("用户名", validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField("邮箱", validators=[DataRequired(), Email()])
    password = PasswordField("密码", validators=[DataRequired(), Length(min=8)])
    password2 = PasswordField("确认密码", validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("注册")


class ForgotPasswordForm(FlaskForm):
    email = StringField("邮箱", validators=[DataRequired(), Email()])
    submit = SubmitField("发送重置链接")


class ResetPasswordForm(FlaskForm):
    password = PasswordField("新密码", validators=[DataRequired(), Length(min=8)])
    password2 = PasswordField("确认新密码", validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("重置密码")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("当前密码", validators=[DataRequired()])
    new_password = PasswordField("新密码", validators=[DataRequired(), Length(min=8)])
    new_password2 = PasswordField("确认新密码", validators=[DataRequired(), EqualTo("new_password")])
    submit = SubmitField("修改密码")


class SetupTOTPForm(FlaskForm):
    code = StringField("TOTP验证码", validators=[DataRequired(), Length(min=6, max=6)])
    submit = SubmitField("启用TOTP")


class DisableTOTPForm(FlaskForm):
    code = StringField("TOTP验证码", validators=[DataRequired(), Length(min=6, max=6)])
    submit = SubmitField("禁用TOTP")


class NicknameForm(FlaskForm):
    nickname = StringField("昵称", validators=[Length(max=64)])
    submit = SubmitField("保存昵称")


class EmailForm(FlaskForm):
    email = StringField("新邮箱", validators=[DataRequired(), Email()])
    submit = SubmitField("更改邮箱")
