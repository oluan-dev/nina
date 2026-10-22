@echo off
rem A Nina sobre o Pipecat: a conversa e do Pipecat, ela so pensa e fala.
rem Uso: clique duas vezes. Fechar esta janela desliga a Nina.
rem Opcoes: --sem-cortar (nao deixa interromper), --deixar-cortar, --fone
title Nina (Pipecat)
cd /d "%~dp0"
set PYTHONIOENCODING=utf8

:de_novo
"%~dp0venv-pipecat\Scripts\python.exe" -m conversa %*
rem 3 = ja tem outra Nina ligada: nao insiste
if errorlevel 3 if not errorlevel 4 (
  echo.
  echo Ja tem uma Nina ligada. Feche a outra janela antes.
  pause
  exit /b
)
rem caiu por qualquer outro motivo: volta sozinha
echo.
echo A Nina caiu. Religando em 5 s... (o motivo fica em diario\conversa.log)
timeout /t 5 /nobreak >nul
goto de_novo
