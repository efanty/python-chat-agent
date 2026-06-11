@echo off

rem "这是注释。下面的代码表示打开一个新的CMD窗口。cmd /k表示窗口打开后执行完命令后不关闭窗口。如果想要关闭，则用/c。"
rem "这是注释。start用来启动一个应用。"
rem '这是注释。 命令1&&命令2&&命令3... 将要执行的多条命令使用引号全部括起来，并且在每个命令用&&分隔。如果只有一条命令，可以不用引号。'
rem '这是注释。 命令1&命令2&命令3... (无论前面命令是否故障，照样执行后面的命令)"
rem "这是注释。 命令1&&命令2&&命令3..(仅当前面命令成功时，才执行后面的命令）"
rem "这是注释。 命令1||命令2||命令3.. (仅当前面命令执行失败时，才执行后面的命令)"
rem "以下是另外一个例子"
rem "@echo off"
rem "cd C:\Users\eliu\OneDrive - CTS Corporation\Desktop\myfolder\software\bing-img"
rem "start pythonw bing-win7.py"
rem "exit(关闭窗口)"

rem "运行虚拟环境并回到主目录后暂停"
start cmd /k "cd G:\desktop\python-projects\langchain-ai\agent_4\venv\Scripts && activate && cd G:\desktop\python-projects\langchain-ai\agent_5"

