from app.agent.load_prompts import sub_agents_config
from app.tools.mysql_tools import list_sql_tables,get_table_data,execute_sql_query

# 本地数据库查询的subagent
db_sub_agent = {
    "name":sub_agents_config["db"].get("name",""),
    "description":sub_agents_config["db"].get("description",""),
    "system_prompt":sub_agents_config["db"].get("system_prompt",""),
    "tools": [list_sql_tables,get_table_data,execute_sql_query]
}


if __name__ == '__main__':
    print(db_sub_agent.get("name"))
