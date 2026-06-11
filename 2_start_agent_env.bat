@echo off


rem "运行虚拟环境并回到主目录后暂停"
start cmd /k "cd venv\Scripts && activate && cd ../.. && python run.py"

