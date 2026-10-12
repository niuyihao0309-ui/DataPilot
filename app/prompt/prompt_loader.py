from pathlib import Path
def loader_prompt(name:str)->str:
    # 根据指定的名称拼接提示词所在的路径
    prompt_path=Path(__file__).parents[2]/"prompts"/f"{name}.prompt"
    # 可以使用Path中的函数直接读取即可
    return prompt_path.read_text(encoding="utf-8")

if __name__ == "__main__":
    prompt_names = [
        "correct_sql",
        "extend_keywords_for_column_recall",
        "extend_keywords_for_metric_recall",
        "extend_keywords_for_value_recall",
        "filter_metric_info",
        "filter_table_info",
        "generate_sql",
        "plan_sql",
    ]
    for name in prompt_names:
        try:
            content = loader_prompt(name)
            print(f"=== {name} ({len(content)} chars) ===")
            print(content[:200], "..." if len(content) > 200 else "")
            print()
        except FileNotFoundError as e:
            print(f"[MISSING] {name}: {e}")








