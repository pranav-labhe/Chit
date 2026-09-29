import json
def load_reasoning_examples(path='data/reasoning.jsonl'):
    return [json.loads(x) for x in open(path,encoding='utf-8') if x.strip()]
def format_reasoning_example(x): return f"Input: {x['input']}\nReasoning: {x['reasoning']}\nAnswer: {x['answer']}\n"
