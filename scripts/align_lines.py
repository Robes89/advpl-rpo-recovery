"""Alinha a reconstrucao as linhas originais (para o debugger posicionar certo).

Usa o source_map de decompilation.json (linha gerada -> linha original gravada no RPO):
reordena as funcoes pela linha original, insere linhas em branco ate cada comando cair na
sua linha e, quando uma macro gerou varios comandos numa mesma linha original (ParamType,
Default, GET MAIL ERROR...), junta-os numa linha so com construcoes equivalentes:
  If C / corpo / EndIf            -> IIf(C, corpo, Nil)
  If C / corpo / Else / alt / EndIf -> IIf(C, corpo, alt)
  a / b (mesma linha)              -> (a, b)
  a / Return X (mesma linha)       -> Return (a, X)
Funcoes cuja numeracao vem de um include (.ch) nao cabem no arquivo e vao para o fim.
Nao altera o .reconstruido verificado: grava NOME.alinhado.<ext> e alignment.json.
"""
from pathlib import Path
from collections import Counter
import json
import re

from checks import lexical

KEYWORDS = re.compile(r'\s*(If|ElseIf|Else|EndIf|Do|Case|Otherwise|EndCase|For|Next|While|EndDo|Return|'
                      r'Local|Static|Private|Public|Begin|Recover|End|Exit|Loop|Function|Method|User|'
                      r'Main|Init|Class|EndClass|Data|Namespace)\b', re.I)
HEADER = re.compile(r'\s*(Static |User |Main |Init |Exit )?(Function|Method)\b', re.I)
ORIGIN = re.compile(r'// Linha original: (\d+)')


def is_expr(text):
    return bool(text.strip()) and not KEYWORDS.match(text)


def indent_of(text):
    return len(text) - len(text.lstrip())


def group(items):
    return items[0] if len(items) == 1 else '(' + ', '.join(items) + ')'


def unmacro_transaction(items, folds):
    """Begin Sequence + BEGINTRAN() ... ENDTRAN() + End Sequence -> Begin/End Transaction.

    E a expansao do comando Begin Transaction (MATA103.PRW: 3 ocorrencias); so reverte o par
    completo, na mesma indentacao e sem Recover no meio.
    """
    items = list(items)
    i = 0
    while i < len(items) - 1:
        text = items[i][0]
        if text.strip().upper() == 'BEGIN SEQUENCE' and items[i+1][0].strip().upper() == 'BEGINTRAN()':
            ind = indent_of(text)
            j = i + 2
            while j < len(items) and not (indent_of(items[j][0]) == ind and items[j][0].strip().upper() in
                                          ('END SEQUENCE', 'RECOVER', 'END')):
                j += 1
            if (j < len(items) and items[j][0].strip().upper() == 'END SEQUENCE'
                    and items[j-1][0].strip().upper() == 'ENDTRAN()'):
                end_tgt = items[j-1][1]
                items[j] = (' '*ind + 'End Transaction', end_tgt)
                del items[j-1]
                items[i] = (' '*ind + 'Begin Transaction', items[i+1][1])
                del items[i+1]
                folds['Begin/End Transaction'] += 1
        i += 1
    return items


def fold(items, folds):
    """Junta comandos que o RPO registra na mesma linha original."""
    items = unmacro_transaction(items, folds)
    # Ramo vazio vira uma linha 'Nil' sem linha original: nao existe no fonte.
    items = [(t, g) for t, g in items if g or t.strip() != 'Nil']
    # Local a, b na mesma linha original: o emissor gera uma declaracao por linha.
    merged = []
    for text, tgt in items:
        decl = re.match(r'(\s*)(Local|Private|Public|Static) (.+)$', text)
        if decl and merged and tgt and merged[-1][1] == tgt:
            prev = re.match(r'\s*(Local|Private|Public|Static) ', merged[-1][0])
            if prev and prev.group(1) == decl.group(2):
                folds['declaracoes na mesma linha'] += 1
                merged[-1] = (merged[-1][0] + ', ' + decl.group(3), tgt)
                continue
        merged.append((text, tgt))
    items = merged
    res, i = [], 0
    while i < len(items):
        text, tgt = items[i]
        m = re.match(r'(\s*)If (.*)$', text)
        if m and tgt:
            ind = len(m.group(1))
            j, body = i + 1, []
            while j < len(items) and items[j][1] == tgt and is_expr(items[j][0]):
                body.append(items[j][0].strip())
                j += 1
            closes = lambda k, word: (k < len(items) and items[k][0].strip().upper() == word
                                      and indent_of(items[k][0]) == ind)
            if body and closes(j, 'ELSE'):
                k, alt = j + 1, []
                while k < len(items) and items[k][1] == tgt and is_expr(items[k][0]):
                    alt.append(items[k][0].strip())
                    k += 1
                if alt and closes(k, 'ENDIF'):
                    folds['IIf com Else'] += 1
                    res.append((' '*ind + f'IIf({m.group(2)}, {group(body)}, {group(alt)})', tgt))
                    i = k + 1
                    continue
            if body and closes(j, 'ENDIF'):
                folds['IIf'] += 1
                res.append((' '*ind + f'IIf({m.group(2)}, {group(body)}, Nil)', tgt))
                i = j + 1
                continue
        res.append(items[i])
        i += 1
    out = []
    for text, tgt in res:
        if out and tgt and out[-1][1] == tgt and is_expr(out[-1][0]):
            prev = out[-1][0]
            pad = prev[:indent_of(prev)]
            ret = re.match(r'\s*Return\s+(.+)$', text, re.I)
            if is_expr(text):
                folds['lista'] += 1
                out[-1] = (pad + f'({prev.strip()}, {text.strip()})', tgt)
                continue
            if ret:
                folds['Return com lista'] += 1
                out[-1] = (pad + f'Return ({prev.strip()}, {ret.group(1).strip()})', tgt)
                continue
        out.append((text, tgt))
    return out


def align(artifact_dir):
    artifact_dir = Path(artifact_dir)
    report = json.loads((artifact_dir/'decompilation.json').read_text(encoding='utf-8'))
    source = artifact_dir/report['source']
    smap = {e['generated_line']: e['original_line'] for e in report['source_map']}
    lines = source.read_text(encoding='utf-8-sig').splitlines()

    blocks, cur = [], {'items': [], 'function': False}
    for number, text in enumerate(lines, 1):
        m = ORIGIN.match(text)
        if m:
            blocks.append(cur)
            cur = {'items': [], 'function': True, 'start': int(m.group(1))}
            continue
        tgt = smap.get(number)
        if cur['function'] and not cur['items'] and HEADER.match(text):
            tgt = cur['start']
        cur['items'].append((text, tgt))
    blocks.append(cur)

    folds = Counter()
    notes = [t for b in blocks if not b['function'] for t, g in b['items'] if t.startswith('// ') and not g]
    # Declaracoes de arquivo (Static fora de funcao) podem estar espalhadas pelo fonte
    # (MATA103: linhas 21 a 27452): cada uma vira um bloco proprio, posicionado pela sua linha.
    loose = []
    for b in [b for b in blocks if not b['function']]:
        for text, tgt in b['items']:
            if tgt:
                loose.append({'items': [(text, tgt)], 'function': False})
            elif loose and text.strip() and not text.startswith('// '):
                loose[-1]['items'].append((text, tgt))
    blocks = [b for b in blocks if b['function']] + loose
    for b in blocks:
        b['items'] = [(t, g) for t, g in fold(b['items'], folds)
                      if not (not g and (t.startswith('// ') or not t.strip()))]
        targets = [g for _, g in b['items'] if g]
        b['first'] = min(targets) if targets else 0
        b['last'] = max(targets) if targets else 0

    out, exact, drift, deferred = [], 0, [], []
    def place(text, tgt):
        nonlocal exact
        if tgt and text.strip().upper() == 'DO CASE':
            tgt -= 1                      # Do Case herda a linha do primeiro Case
        if tgt:
            while len(out) + 1 < tgt:
                out.append('')
            if len(out) + 1 == tgt:
                exact += 1
            else:
                drift.append({'original_line': tgt, 'placed_line': len(out) + 1, 'text': text.strip()[:80]})
        out.append(text)

    ordered = sorted([b for b in blocks if b['items']], key=lambda b: b['first'])
    if ordered and ordered[0]['first'] > len(notes) + 1:
        out.extend(notes)
    for b in ordered:
        if b['function'] and b['first'] and b['first'] < len(out) + 1:
            deferred.append(b)            # numeracao de outro arquivo (include)
            continue
        for text, tgt in b['items']:
            place(text, tgt)
    if deferred:
        out += ['', '// ' + '-'*70,
                '// Funcoes vindas de arquivos de include (#include): a numeracao de linha',
                '// delas se refere ao include, nao a este fonte, por isso ficam aqui no fim.',
                '// ' + '-'*70]
        for b in deferred:
            out += ['', f"// Linhas {b['first']}-{b['last']} do arquivo de include"]
            out += [t for t, _ in b['items']]

    text = '\n'.join(out) + '\n'
    lexical(text)
    destination = artifact_dir/source.name.replace('.reconstruido', '.alinhado')
    destination.write_text(text, encoding='utf-8-sig', newline='\r\n')
    mapped = exact + len(drift)
    result = {'status': 'aligned', 'source': destination.name, 'lines': len(out),
              'mapped_statements': mapped, 'exact_line': exact,
              'exact_ratio': round(exact / mapped, 4) if mapped else None,
              'displaced': len(drift), 'include_functions_moved_to_end': len(deferred),
              'folds': dict(folds), 'displaced_sample': drift[:50],
              'limitation': 'Juncoes reescrevem macros em IIf/listas equivalentes; nao recompilado.'}
    (artifact_dir/'alignment.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    return result
