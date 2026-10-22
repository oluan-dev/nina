# A Nina viva por conta própria: sobe com o Windows e volta sozinha se cair.
#
# Para usar, crie uma tarefa agendada (ex.: "Nina", ao fazer logon e a cada
# 5 min) que rode:
#   powershell -NoProfile -ExecutionPolicy Bypass -File <pasta>\nina-sempre.ps1
# Não depende de nenhuma sessão do Claude.

$raiz = $PSScriptRoot
$python = Join-Path $raiz "venv-pipecat\Scripts\python.exe"
$trava = Join-Path $raiz "nina.lock"
$log = Join-Path $raiz "diario\sessao.log"
$env:PYTHONIOENCODING = "utf8"
# a tarefa agendada começa em outra pasta: sem isto o Python não acha o módulo
Set-Location $raiz

# já tem uma Nina de pé? então não faço nada (a tarefa roda de novo a cada 5 min)
if (Test-Path $trava) {
  $pid_antigo = (Get-Content $trava -ErrorAction SilentlyContinue | Select-Object -First 1)
  if ($pid_antigo -and (Get-Process -Id $pid_antigo -ErrorAction SilentlyContinue)) { exit 0 }
  Remove-Item $trava -Force -ErrorAction SilentlyContinue
}

# sobra de sessão anterior disputa o microfone do celular
Get-Process scrcpy -ErrorAction SilentlyContinue | Stop-Process -Force

New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
while ($true) {
  & $python -m conversa *>> $log
  # caiu: espera um pouco e sobe de novo, para não ficar em laço apertado
  Start-Sleep -Seconds 5
  Remove-Item $trava -Force -ErrorAction SilentlyContinue
}
