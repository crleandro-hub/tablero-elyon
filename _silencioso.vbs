' =====================================================
'  GRUPO ELYON - Lanzador silencioso
' =====================================================
'  Corre actualizar_auto.bat SIN ventana.
'
'  Por que existe: el Programador de tareas ejecutaba el .bat directamente y
'  cmd.exe abria su ventana negra en primer plano cada dos horas, en medio
'  del trabajo. Windows no tiene forma de pedirle a una tarea que abra el
'  .bat minimizado; lo que si se puede es lanzarlo desde aca con estilo de
'  ventana 0, que es "sin ventana".
'
'  El tercer parametro en True hace que este script ESPERE a que termine el
'  .bat. Sin eso la tarea se daria por terminada al instante y el limite de
'  30 minutos no serviria para cortar una corrida colgada.
'
'  Para correr el tablero a mano y VER lo que hace, esta
'  2-ACTUALIZAR-TABLERO.bat, que no pasa por aca.
' =====================================================

Dim sh, fso, carpeta, bat
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

carpeta = fso.GetParentFolderName(WScript.ScriptFullName)
bat     = carpeta & "\actualizar_auto.bat"

If Not fso.FileExists(bat) Then
    WScript.Quit 2
End If

sh.CurrentDirectory = carpeta
WScript.Quit sh.Run("""" & bat & """", 0, True)
