"""Expand the English foundation streams using literal source pools in data2.py.

data2.py is an extension module whose base data.py is not present beside it, so
this script reads its literal pools with AST instead of importing/executing it.
It preserves each destination file's existing format and records a fixed seed.
"""
from __future__ import annotations

import ast
import hashlib
import json
import random
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"C:\Python\data2.py")
BASELINES = ROOT / "docs/benchmarks/dataset-baselines"
TARGET_BYTES = 1_048_576
SEED = 777  # same fixed random seed declared by data2.py


def safe_literal(node):
    """Evaluate only literal AST nodes and dict(keyword=value) constructors."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [safe_literal(x) for x in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(safe_literal(x) for x in node.elts)
    if isinstance(node, ast.Set):
        return {safe_literal(x) for x in node.elts}
    if isinstance(node, ast.Dict):
        return {safe_literal(k): safe_literal(v) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
        return {kw.arg: safe_literal(kw.value) for kw in node.keywords}
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "split":
        source = safe_literal(node.func.value)
        separator = safe_literal(node.args[0]) if node.args else None
        if isinstance(source, str):
            return source.split(separator)
    raise ValueError(f"Not a permitted literal: {ast.dump(node, include_attributes=False)[:180]}")


def source_pools() -> dict:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    names = {"_F2", "_M2", "_ROLES", "G", "ADJS", "IRR", "V_DEF", "THEMES",
             "STEPS", "USES", "POLITE", "FACTS", "CLARIFY", "_V2", "ADJPREP",
             "COUNT_N", "MASS_N", "EMO", "EVT", "HELPS", "REASON"}
    pools = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [x.id for x in node.targets if isinstance(x, ast.Name)]
            for name in targets:
                if name in names:
                    try:
                        value = node.value
                        if (isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add)
                                and isinstance(value.left, ast.Name) and value.left.id == name):
                            value = value.right
                        pools[name] = safe_literal(value)
                    except ValueError:
                        pass
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            if name in names:
                try:
                    pools[name] = safe_literal(node.value)
                except ValueError:
                    pass
    missing = names - pools.keys()
    if missing:
        raise RuntimeError(f"Could not read source pools from {SOURCE}: {sorted(missing)}")
    return pools


def split_items(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"\n\s*\n", text) if x.strip()]


def append_to_target(path: Path, make_item, rng: random.Random) -> tuple[int, int, str]:
    original = path.read_text(encoding="utf-8").rstrip()
    items = split_items(original)
    seen = set(items)
    additions = []
    size = len(original.encode("utf-8"))
    attempts = 0
    while size < TARGET_BYTES:
        attempts += 1
        if attempts > TARGET_BYTES * 40:
            raise RuntimeError(f"Unique generation stalled for {path}")
        # Advance the family selector even when a candidate duplicates an
        # existing item; otherwise a finite family can get stuck retrying it.
        item = make_item(rng, attempts)
        if item in seen:
            continue
        seen.add(item)
        additions.append(item)
        size += len(item.encode("utf-8")) + 2
    content = original + "\n\n" + "\n\n".join(additions) + "\n"
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(content, encoding="utf-8", newline="\n")
    temp.replace(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return len(items), len(additions), digest


def article_for(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" and not re.match(r"(uni|use|one|eu)", word.lower()) else "a"


def third_person(verb: str) -> str:
    if verb.endswith("y") and verb[-2].lower() not in "aeiou":
        return verb[:-1] + "ies"
    if re.search(r"(s|sh|ch|x|z|o)$", verb):
        return verb + "es"
    return verb + "s"


def past_forms(verb: str, irregular: dict) -> tuple[str, str]:
    if verb in irregular:
        return irregular[verb]
    if verb.endswith("e"):
        past = verb + "d"
    elif verb.endswith("y") and verb[-2].lower() not in "aeiou":
        past = verb[:-1] + "ied"
    elif (len(verb) > 2 and verb[-1] not in "aeiouwxy" and verb[-2] in "aeiou"
          and verb[-3] not in "aeiou"):
        past = verb + verb[-1] + "ed"
    else:
        past = verb + "ed"
    return past, past


def subjects(pools: dict) -> list[str]:
    return pools["_F2"] + pools["_M2"] + ["the " + x for x in pools["_ROLES"]]


def noun_options(pools: dict, group: str) -> list[tuple[str, str]]:
    out = []
    for token in pools["G"][group].split():
        parts = token.split(":")
        out.append((parts[0], parts[1] if len(parts) > 1 else "c"))
    return out


ADJ_ALIAS = {"docsign": "doc", "stirrable": "food", "boilable": "food", "fryable": "food",
             "bakeable": "food", "sliceable": "food", "wipeable": "obj", "lockable": "obj",
             "paintable": "obj", "unpackable": "obj"}
GROUP_CLASS = {"doc": "doc", "docsign": "doc", "food": "food", "stir": "food", "cook": "food",
               "boil": "food", "fry": "food", "bake": "food", "slice": "food", "obj": "obj",
               "wipe": "obj", "lock": "obj", "paint": "obj", "unpack": "obj", "plants": "plants",
               "crops": "crops", "places": "places", "cross": "places"}


def noun_phrase(rng: random.Random, pools: dict, group: str) -> tuple[str, str]:
    noun, form = rng.choice(noun_options(pools, group))
    alias = ADJ_ALIAS.get(group, group)
    adjectives = pools["ADJS"].get(alias, [])
    adjective = (rng.choice(adjectives) + " ") if adjectives and rng.random() < 0.38 else ""
    head = adjective + noun
    if form == "p":
        det = rng.choice(["the", "some", "my", "our", "two", "three", "several", "these"])
    elif form == "m":
        det = rng.choice(["the", "some", "my", "our", "a little"])
    else:
        det = rng.choice(["the", "my", "our", "this", "that", "her", "his", "a", "an"])
        if det in ("a", "an"):
            det = article_for(head)
    return f"{det} {head}", form


def structural_generator(pools: dict):
    rng = random.Random(SEED + 101)
    verbs = []
    for family, (bases, groups) in pools["V_DEF"].items():
        if family not in GROUP_CLASS:
            continue
        for base in bases:
            for group in groups:
                if group in pools["G"]:
                    verbs.append((base, family, group))
    single_subjects = subjects(pools)
    plural_subjects = ["the children", "my neighbors", "the workers", "the guests", "the students",
                       "the visitors", "the volunteers", "the players", "the twins", "the farmers",
                       "the tourists", "the residents", "the engineers", "the cooks", "our friends",
                       "the musicians", "the delegates", "the shoppers", "the sailors", "the cleaners"]
    reasons = pools["REASON"]
    prepositions = pools["ADJPREP"]
    count_nouns = pools["COUNT_N"]
    mass_nouns = pools["MASS_N"]

    def make(_random: random.Random, index: int) -> str:
        family = index % 12
        verb, group, noun_group = rng.choice(verbs)
        base = verb
        past, participle = past_forms(base, pools["IRR"])
        present3 = third_person(base)
        obj, form = noun_phrase(rng, pools, noun_group)
        subject = rng.choice(single_subjects)
        if family == 0:
            prompt = f"Rewrite in the simple past: {subject} {present3} {obj}."
            answer = f"{subject} {past} {obj}."
        elif family == 1:
            plural = rng.choice(plural_subjects)
            prompt = f"Choose the correct verb: {plural} ___ {obj}."
            answer = f"{plural} {base} {obj}."
        elif family == 2:
            prompt = f"Turn this into a yes-or-no question: {subject} {present3} {obj}."
            answer = f"Does {subject} {base} {obj}?"
        elif family == 3:
            auxiliary = "were" if form == "p" else "was"
            prompt = f"Change to passive voice: {subject} {past} {obj}."
            answer = f"{obj[0].upper() + obj[1:]} {auxiliary} {participle} by {subject}."
        elif family == 4:
            prompt = f"Make this sentence negative without changing tense: {subject} {past} {obj}."
            answer = f"{subject} did not {base} {obj}."
        elif family == 5:
            singulars = [n for n, kind in noun_options(pools, noun_group) if kind == "c"]
            if not singulars:
                singulars = [n for n, kind in noun_options(pools, "obj") if kind == "c"]
            noun = rng.choice(singulars)
            prompt = f"Choose 'a' or 'an': {subject} packed ___ {noun} before leaving."
            answer = f"{subject} packed {article_for(noun)} {noun} before leaving."
        elif family == 6:
            adjective, prep = rng.choice(prepositions)
            name = rng.choice(pools["_F2"] + pools["_M2"])
            prompt = f"Complete the sentence with the usual preposition: {name} is {adjective} ___ the result."
            answer = f"{name} is {adjective} {prep} the result."
        elif family == 7:
            if rng.random() < 0.5:
                noun = rng.choice(count_nouns)
                prompt = f"Choose 'fewer' or 'less': We have ___ {noun} to check."
                answer = f"We have fewer {noun} to check."
            else:
                noun = rng.choice(mass_nouns)
                prompt = f"Choose 'fewer' or 'less': We have ___ {noun} to use."
                answer = f"We have less {noun} to use."
        elif family == 8:
            phrase, phrase_form = noun_phrase(rng, pools, noun_group)
            subject = rng.choice(single_subjects)
            aux = "are" if phrase_form == "p" else "is"
            prompt = f"Complete with the correct form of 'be': {subject} and {phrase} ___ ready."
            answer = f"{subject} and {phrase} are ready."
        elif family == 9:
            cls = GROUP_CLASS.get(group, "doc")
            reason = rng.choice(reasons.get(cls, reasons["doc"]))
            action = f"{subject} {past} {obj}"
            prompt = f"Join the ideas with 'because': {action}. {reason.capitalize()}."
            answer = f"{action[0].upper() + action[1:]} because {reason}."
        elif family == 10:
            prompt = f"Identify the direct object: {subject} {past} {obj}."
            answer = f"The direct object is {obj}."
        else:
            prompt = f"Correct the punctuation and capitalization: after the task {subject} checked {obj} before leaving"
            answer = f"After the task, {subject} checked {obj} before leaving."
        return f"Task: chat\nUser: {prompt}\nChit: {answer}"
    return make


def scene(rng: random.Random, pools: dict) -> tuple[str, str, str]:
    theme_name = rng.choice(list(pools["THEMES"]))
    theme = pools["THEMES"][theme_name]
    person = rng.choice(pools["_F2"] + pools["_M2"])
    opening, action, detail, ending = (rng.choice(theme[k]) for k in ("open", "act", "det", "end"))
    paragraph = f"{opening} {person} {action}. {detail} Later, {person} {ending}."
    return paragraph, person, action


def lexical_generator(pools: dict):
    rng = random.Random(SEED + 202)
    def make(_random: random.Random, _index: int) -> str:
        return scene(rng, pools)[0]
    return make


def conversation_generator(pools: dict):
    rng = random.Random(SEED + 303)
    steps, uses = pools["STEPS"], pools["USES"]
    polite, facts, clarify = pools["POLITE"], pools["FACTS"], pools["CLARIFY"]
    emotions = ["anxious", "hopeful", "pressured", "uncertain", "tired", "restless", "jittery", "tense", "grateful", "disappointed", "curious", "overwhelmed"] + pools["EMO"]
    events = ["I have a difficult conversation tomorrow", "I am starting something unfamiliar", "I need to ask someone for help", "I made a mistake and want to repair it", "I am waiting for an important reply", "I have more tasks than time today"] + pools["EVT"]
    helps = ["one small next step", "a brief checklist", "a practice question", "a calm opening sentence", "a short pause", "help sorting what is urgent"] + pools["HELPS"]
    vocab = []
    for line in pools["_V2"].strip().splitlines():
        fields = line.split("|")
        if len(fields) == 5:
            vocab.append(tuple(fields))
    people = pools["_F2"] + pools["_M2"]
    prompt_styles = [
        "How can I {task}? Give me clear steps.",
        "I am trying to {task}. What is a sensible way to begin?",
        "Please explain how to {task} in a few manageable steps.",
        "I am new to this. Could you guide me through how to {task}?",
        "What should I do to {task}? Keep the instructions practical.",
    ]

    def make(_random: random.Random, index: int) -> str:
        mode = index % 9
        if mode == 0:
            task, answer_steps = rng.choice(steps)
            prompt = rng.choice(prompt_styles).format(task=task)
            answer = " ".join(answer_steps)
        elif mode == 1:
            item, purpose = rng.choice(uses)
            prompt = rng.choice([f"What is a {item} used for?", f"How could I use a {item}?", f"Name the practical purpose of a {item}.", f"I found a {item}. What does it help someone do?"])
            answer = f"A {item} is used to {purpose}."
        elif mode == 2:
            blunt, kind = rng.choice(polite)
            prompt = rng.choice([f"Rewrite this request politely without changing what it asks: {blunt}", f"A colleague wrote, '{blunt}' Make the wording considerate.", f"Could you soften this message while preserving its meaning? {blunt}"])
            answer = kind
        elif mode == 3:
            question, answer = rng.choice(facts)
            prompt = rng.choice([question, f"Please answer briefly: {question}", f"I am checking a basic fact. {question}"])
        elif mode == 4:
            question, answer = rng.choice(clarify)
            prompt = rng.choice([question, f"A user says, '{question}' What should Chit ask before guessing?", f"Respond to this underspecified request by clarifying: {question}"])
        elif mode == 5:
            feeling = rng.choice(emotions); event = rng.choice(events); help_offer = rng.choice(helps)
            prompt = rng.choice([f"I feel {feeling}. {event}. Could you offer {help_offer}?", f"{event}. I am feeling {feeling}; please respond without judging me.", f"I feel {feeling} about this: {event}. Ask one gentle question and don't rush to fix it."])
            answer = rng.choice([f"Thank you for telling me. It makes sense that you feel {feeling}. We can take this one step at a time. Would {help_offer} be useful right now?", f"That sounds like a lot to hold. I won't assume what you need. Would {help_offer} help, or would you rather talk first?", f"I hear that this feels difficult. You do not have to solve everything at once. What part would you like me to listen to first?"])
        elif mode == 6:
            paragraph, person, action = scene(rng, pools)
            prompt = f"Read this scene and answer from its details:\n{paragraph}\nWhat did {person} do?"
            answer = f"{person} {action}."
        elif mode == 7:
            word, pos, definition, example, synonym = rng.choice(vocab)
            prompt = rng.choice([f"What does '{word}' mean? Include a short example.", f"Explain the word '{word}' for an English learner.", f"Give the meaning and one example of '{word}'."])
            answer = f"{word.capitalize()} means {definition}. Example: {example}"
        else:
            name = rng.choice(people); task, answer_steps = rng.choice(steps)
            prompt = rng.choice([f"{name} has low energy but wants to {task}. Suggest a gentle first step.", f"Help {name} begin to {task} without making a demanding plan.", f"{name} feels uncertain about how to {task}. What would be one manageable start?"])
            answer = f"{answer_steps[0]} Start with just that step, then decide whether you have energy for more."
        return f"Task: chat\nUser: {prompt}\nChit: {answer}"
    return make


def update_manifest(pools: dict) -> None:
    manifest_path = ROOT / "data/english_foundation/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dataset_version"] = "english-foundation-v1-data2-expanded"
    manifest["authorship"] = "project-authored-and-synthetic-from-data2-pools"
    for row in manifest["sources"]:
        path = ROOT / row["path"]
        if path.name in {"conversation.txt", "lexical_prose.txt", "structural.txt"}:
            raw = path.read_bytes()
            row["sha256"] = hashlib.sha256(raw).hexdigest()
            row["utf8_bytes"] = len(raw)
            row["items"] = len(split_items(raw.decode("utf-8")))
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Expected source generator: {SOURCE}")
    pools = source_pools()
    outputs = [
        (ROOT / "data/english_foundation/conversation.txt", conversation_generator(pools), SEED + 303),
        (ROOT / "data/english_foundation/lexical_prose.txt", lexical_generator(pools), SEED + 202),
        (ROOT / "data/english_foundation/structural.txt", structural_generator(pools), SEED + 101),
    ]
    BASELINES.mkdir(parents=True, exist_ok=True)
    for path, _make, _seed in outputs:
        backup = BASELINES / f"{path.stem}-pre-data2-expansion-2026-10-04.txt"
        if not backup.exists():
            shutil.copyfile(path, backup)
    summaries = []
    for path, make, seed in outputs:
        before, added, digest = append_to_target(path, make, random.Random(seed))
        summaries.append((path.name, before, added, path.stat().st_size, digest))
    update_manifest(pools)
    for name, before, added, size, digest in summaries:
        print(f"{name}: {before:,} existing items preserved; {added:,} distinct items added; {size:,} bytes; sha256={digest}")


if __name__ == "__main__":
    main()
