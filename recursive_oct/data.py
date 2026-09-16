"""User-only extraction, conservative curation, and pre-trajectory bank selection."""
from __future__ import annotations
import json
import math
import random
import re
import unicodedata
from collections import Counter
from pathlib import Path

VALUE_PATTERNS = {
    'honesty': r'\b(honest\w*|dishonest\w*|lying|lie|lies|truth\w*|deceiv\w*|deception|integrity)\b',
    'compassion': r'\b(compassion\w*|empathy|sympathy|griev\w*|grief|lonely|loneliness|bereav\w*|bully\w*|bullying|kindness|forgive\w*|forgiveness)\b',
    'autonomy': r'\b(autonomy|consent|coerc\w*|manipulat\w*|boundaries|independen\w*|personal choice)\b',
    'fairness': r'\b(fairness|unfair\w*|discrimination|discriminatory|discriminating against|racism|racist|sexism|sexist|equal rights|inequality|prejudice|bias(?:es|ed)?)\b',
    'privacy': r'\b(privacy|private information|confidential\w*|personal data|surveillance|secret\w*)\b',
    'uncertainty': r'\b(uncertain\w*|unsure|evidence|reliable|misinformation|skeptic\w*|doubt\w*)\b',
    'disagreement': r'\b(disagree\w*|conflict\w*|criticis\w*|criticiz\w*|different opinions|argument\w*)\b',
    'loyalty': r'\b(loyal\w*|betray\w*|trust\w*|friendship|friend\w*|family|coworker\w*|colleague\w*)\b',
    'stakeholders': r'\b(ethical|ethics|moral\w*|responsibilit\w*|community|communities|environmental impact|society|social impact|public interest)\b',
}

def value_tags(prompt: str) -> list[str]:
    tags=[k for k, p in VALUE_PATTERNS.items() if re.search(p, prompt, re.I)]
    if 'loyalty' in tags and not re.search(r'\b(?:loyal\w*|betray\w*|trust|friendship|relationship\w*|should|advice|help|support|talk|handle|cope|difficult|communicat\w*|forgiv\w*|disagree\w*|convinc\w*)\b',prompt,re.I):
        tags.remove('loyalty')
    if 'honesty' in tags and re.search(r'\blying (?:leg|down|position)\b',prompt,re.I): tags.remove('honesty')
    if 'autonomy' in tags and re.search(r'\b(?:independently|declaration of independence)\b',prompt,re.I) and not re.search(r'\b(?:consent|coerc\w*|manipulat\w*|boundaries|autonomy)\b',prompt,re.I): tags.remove('autonomy')
    if 'disagreement' in tags and re.search(r'\b(?:git|database|sync\w*|db|code|programming)\b',prompt,re.I) and not re.search(r'\b(?:disagree\w*|critic\w*|opinion\w*)\b',prompt,re.I): tags.remove('disagreement')
    return tags

def normalized_prompt(text: str) -> str:
    return ' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', text).casefold()))

def extract_helpsteer_user(row: dict) -> str | None:
    """HelpSteer2 prompt may serialize multi-turn history using extra_id_1."""
    text=row.get('prompt')
    if not isinstance(text,str): return None
    text=re.sub(r'^\s*<extra_id_1>User\s*','',text)
    return re.split(r'<extra_id_\d+>|\n\n(?:Assistant|Human|User):',text,maxsplit=1)[0].strip()

def extract_hh_user(row: dict) -> str | None:
    """Only first Human span; compare branches without consuming assistant text."""
    def first(text):
        match=re.match(r'^\s*Human:\s*(.*?)\n\nAssistant:', text, re.S)
        return match.group(1).strip() if match else None
    left, right = first(row.get('chosen','')), first(row.get('rejected',''))
    return left if left and left == right else None

def extract_wildchat_user(row: dict) -> str | None:
    conversation=row.get('conversation',[])
    if not conversation or conversation[0].get('role') != 'user':
        return None
    # Never take a later user turn: it can depend on an excluded assistant turn.
    return conversation[0].get('content')

def exclusion_reason(text: str | None) -> str | None:
    if not isinstance(text,str) or not text.strip(): return 'empty'
    words=text.split()
    if re.search(r'[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]|\ufffd',text): return 'nonenglish_or_corrupt'
    if '<extra_id_' in text: return 'serialized_history'
    if len(words)<7 or len(words)>320 or len(text)>2400: return 'length'
    if len(re.findall(r'[A-Za-z]',text))/max(len(text),1)<0.55: return 'nonprose'
    patterns={
      'private_data': r'(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b\d{3}[- .]\d{2}[- .]\d{4}\b|\b(?:\+?\d[\d ()-]{8,}\d)\b|\b\d+\s+\w+(?:\s+\w+)?\s+(?:street|avenue|road|lane|drive|st\.|ave\.)\b)',
      'personal_detail': r'\b(?:born (?:on|in)|date of birth|my full name|my address|my phone|my real name|PO Box)\b',
      'credentials': r'(?:\b(?:sk|hf)_[A-Za-z0-9]{12,}|sk-[A-Za-z0-9]{12,}|AKIA[A-Z0-9]{16}|BEGIN .*PRIVATE KEY|(?:password|api[_ -]?key|access[_ -]?token)\s*(?:is|:|=)\s*\S+)',
      'unavailable_media': r'(?:\b(?:attached|uploaded|this|above|following)\s+(?:image|picture|photo|screenshot|diagram|file|pdf|document)\b|<image>|\[image\]|https?://|\bimage\s*\d+\b)',
      'setup_without_request': r'(?:\b(?:reply (?:me )?ok|just (?:reply|say) (?:ok|yes)|just digest this|my next prompt|i will (?:give|provide|send) you|ready to|are you ready)\b|\b(?:using|based on|as follows)\s*[:.]?\s*$)',
      'context_fragment': r'(?:^\s*(?:continue|go on|yes[, .!]|no[, .!]|thanks|thank you|do the same|try again|rewrite it|explain it|make it|what about|and what|now do)\b|\b(?:previous (?:answer|response|conversation)|as (?:mentioned|discussed) (?:above|earlier)|text above|code above|above text|above code)\b|\[\s*(?:insert|your|redacted)\b)',
      'adversarial_or_explicit': r'\b(?:jailbreak|DAN mode|Do Anything Now|pooping|defecat\w*|diaper\w*|swingers|rogue AI|incel|Neurosemantical|outside legality|ignore (?:all |the )?(?:previous|prior) instructions|uncensored|rape|raping|porn\w*|sex scene|sexual intercourse|nigger\w*|suicide method|make a bomb|build a bomb|steal (?:a|someone)|hack (?:into|someone))\b',
    }
    for reason,pattern in patterns.items():
        if re.search(pattern,text,re.I): return reason
    if len(words)<16 and re.search(r'^\s*(?:act as|take on the persona|you are a)',text,re.I): return 'setup_without_request'
    # Requests with a missing supplied object, often fragments in scraped chat.
    if re.search(r'\b(?:the following|below)\s*[:.]?\s*$',text,re.I): return 'missing_object'
    return None

def load_prompt_bank(path: str | Path) -> list[dict]:
    with Path(path).open() as f:
        rows=[json.loads(line) for line in f if line.strip()]
    ids=[r['id'] for r in rows]; prompts=[normalized_prompt(r['prompt']) for r in rows]
    if len(set(ids))!=len(ids) or len(set(prompts))!=len(prompts):
        raise ValueError('Prompt bank contains duplicate IDs or normalized prompts')
    if any('response' in r or 'chosen' in r or 'rejected' in r for r in rows):
        raise ValueError('Prompt bank must contain user inputs only')
    return rows

def select_stratified_subset(rows: list[dict], size: int, seed: int=20260915) -> list[dict]:
    """Deterministic proportional subset, selected ONLY before trajectory start."""
    if not 0 < size <= len(rows): raise ValueError('size must be in [1, bank size]')
    groups={c:[r for r in rows if r['category']==c] for c in sorted({r['category'] for r in rows})}
    quotas={c:math.floor(len(g)*size/len(rows)) for c,g in groups.items()}
    residual=sorted(groups,key=lambda c:(-(len(groups[c])*size/len(rows)-quotas[c]),c))
    for c in residual[:size-sum(quotas.values())]: quotas[c]+=1
    rng=random.Random(seed); result=[]
    for c,g in groups.items():
        ordered=list(g); rng.shuffle(ordered); result.extend(ordered[:quotas[c]])
    rng.shuffle(result)
    return result

def write_jsonl(path: str | Path, rows: list[dict]) -> None:
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
