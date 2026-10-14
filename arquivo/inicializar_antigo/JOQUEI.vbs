' Sobe o agente do JOQUEI junto com o Windows, sem janela.
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\agent"
sh.Run "pythonw joquei_agent.py", 0, False
