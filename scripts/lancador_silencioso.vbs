' Lancador silencioso do FLUXO PRO — sem janela, mas COM codigo de saida.
'
' Por que existe, se ja ha um lancador silencioso generico:
' o generico roda com `False` (nao espera o processo) e nao devolve codigo
' nenhum, entao `wscript.exe` termina na hora com 0. Com ele, a tarefa do
' Windows marca SUCESSO qualquer que seja o resultado do script — foi assim
' que `FluxoPro-GravarPregao` reportou "resultado 0" em 01/09 e 02/09/2026 sem
' ter gravado pregao nenhum.
'
' Aqui:
'   True  = ESPERA o processo terminar (a tarefa fica "Em execucao" durante o
'           pregao, que e a verdade — e o Agendador nao dispara uma segunda
'           instancia por cima);
'   Quit  = PROPAGA o codigo, para o portao de "zero negocios" do supervisor
'           chegar ate o Agendador em vez de morrer no log.
'
' O lancador generico NAO foi alterado de proposito: ele e compartilhado com
' outras rotinas, e mudar "nao espera" para "espera" mudaria o comportamento
' de todas elas.
'
' Uso: wscript.exe lancador_silencioso.vbs "caminho\script.cmd" ["arg1"] ...

Set WshShell = CreateObject("WScript.Shell")

cmdLine = ""
For i = 0 To WScript.Arguments.Count - 1
    cmdLine = cmdLine & """" & WScript.Arguments(i) & """ "
Next

' 0 = janela oculta ; True = espera terminar e devolve o codigo de saida
codigo = WshShell.Run(cmdLine, 0, True)
WScript.Quit(codigo)
