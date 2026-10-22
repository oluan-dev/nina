// Rodar script fora da pasta da Nina é coisa séria: pede o "sim" falado.
//
// A lista de perigo do cerebro.mjs só conhece apagar, git push e afins; rodar
// um script de outro projeto passaria sem perguntar. Os comandos dela mesma
// (scripts dentro desta pasta) seguem livres.
//
// O caminho é RESOLVIDO (pasta do `cd`, `..`, link) e comparado com a pasta da
// Nina por prefixo com separador: comparar texto deixava passar
// `C:/outra/nina/pagar.py` e `nina/../../outro/x.py`.
import { existsSync, realpathSync } from "node:fs";
import { dirname, isAbsolute, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = realpathSync(resolve(dirname(fileURLToPath(import.meta.url)), ".."));
const INTERPRETE = String.raw`(?:^|[\s;&|("'])(?:\S*[\\/])?(?:python3?|py|node|pwsh|powershell|bash|sh|cmd)(?:\.exe)?["']?`;
const SCRIPT = /["']?([^"'\s]+\.(?:py|js|mjs|cjs|ps1|bat|cmd|sh))\b/gi;
const CD = /^\s*cd\s+(?:\/d\s+)?("[^"]*"|'[^']*'|\S+)\s*&&/i;

function deGitBash(p) {
  // /c/Users/... -> C:/Users/... (o Bash dela é o Git Bash)
  return p.replace(/^\/([a-z])\//i, (_, l) => `${l.toUpperCase()}:/`);
}

function dentroDaNina(caminho, pasta) {
  if (caminho.split(/[\\/]/).includes("..")) return false;    // `..`: trata como de fora
  let real = isAbsolute(deGitBash(caminho)) ? deGitBash(caminho) : resolve(pasta, caminho);
  try {
    if (existsSync(real)) real = realpathSync(real);
  } catch {
    return false;                         // não deu para resolver: de fora
  }
  const r = resolve(real).toLowerCase(), raiz = RAIZ.toLowerCase();
  return r === raiz || r.startsWith(raiz + sep);
}

export function rodaScriptDeFora(cmd, pasta = RAIZ) {
  const c = String(cmd ?? "");
  if (!new RegExp(INTERPRETE, "i").test(c) && !/^\s*\.?[\\/]?[^\s]+\.(?:bat|cmd|ps1)\b/i.test(c)) {
    return false;
  }
  const cd = c.match(CD);
  if (cd) pasta = resolve(pasta, deGitBash(cd[1].replace(/^["']|["']$/g, "")));
  for (const m of c.matchAll(SCRIPT)) {
    if (!dentroDaNina(m[1].replace(/\\/g, "/"), pasta)) return true;
  }
  return false;
}
