// Rodar script de outro projeto pede o "sim" falado; os da própria Nina, não.
//
//   node testes/teste_perigo.mjs
import assert from "node:assert/strict";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { rodaScriptDeFora } from "../nina/perigo.mjs";

const barra = (p) => p.split("\\").join("/");
const RAIZ = barra(resolve(dirname(fileURLToPath(import.meta.url)), ".."));
const FORA = barra(resolve(RAIZ, "..", "outro-projeto"));
const gitBash = (p) => p.replace(/^([A-Za-z]):/, (_, l) => `/${l.toLowerCase()}`);

for (const de_fora of [
  `cd ${FORA} && python -I "${FORA}/tmp/pagamentos.py" 2>&1 | tail -20`,
  `python ${FORA.split("/").join("\\")}\\pagar.py`,
  `node "${FORA}/enviar.js"`,
  `powershell -File ${FORA}/provisionar.ps1`,
  `${FORA}/publicar.bat`,
]) assert.ok(rodaScriptDeFora(de_fora), `devia pedir licença: ${de_fora}`);

for (const dela of [
  `cd ${RAIZ} && python gerar_bordoes.py`,
  `python ${RAIZ}/testes/teste_conversa_regras.py`,
  `cat "${FORA}/notas.md"`,
  `ls ${FORA}`,
  `grep -rn total "${FORA}" | head`,
]) assert.ok(!rodaScriptDeFora(dela), `não devia pedir licença: ${dela}`);
console.log("ok: script de outro projeto pede o sim; os dela, não");

// Comparar texto deixaria passar estes.
for (const furo of [
  `python ${FORA}/nina/pagar.py`,
  `python nina/../../outro-projeto/x.py`,
  `cd ${FORA} && python testes/x.py`,
  `python ${gitBash(FORA)}/enviar.py`,
]) assert.ok(rodaScriptDeFora(furo), `devia pedir licença: ${furo}`);
assert.ok(!rodaScriptDeFora(`python ${gitBash(RAIZ)}/testes/teste_conversa_regras.py`));
assert.ok(!rodaScriptDeFora(`cd ${gitBash(RAIZ)} && python testes/teste_conversa_regras.py`));
console.log("ok: caminho resolvido, sem furo por texto nem por ..");
