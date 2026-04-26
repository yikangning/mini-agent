"""
tools/definitions.py
--------------------
工具的 JSON Schema 定义 —— 这是告诉 LLM "有哪些工具可用"的部分。

对标 claw-code: src/tools.py (工具元数据) + rust/crates/tools/src/lib.rs (mvp_tool_specs)
扩展方式: 直接在 TOOLS 列表里追加新工具的 schema dict。
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前日期和时间。当用户询问现在几点、今天几号、星期几等时间相关问题时使用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取指定路径的文件内容。当用户要求查看、读取某个文件时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径，可以是相对路径或绝对路径",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出指定目录下的所有文件。当用户要求查看目录内容时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录路径，不填则默认为当前目录",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "将内容写入文件。文件不存在时自动创建，存在时覆盖。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件路径",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的完整内容",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "执行 bash 命令并返回输出。用于查看系统状态、运行脚本等操作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的完整 bash 命令",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "对文件进行精准的局部替换。将 old_str 替换为 new_str，"
                "要求 old_str 在文件中唯一存在。"
                "适用于修改部分代码，而不是重写整个文件。"
                "修改前请先用 read_file 确认 old_str 的确切内容。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要编辑的文件路径",
                    },
                    "old_str": {
                        "type": "string",
                        "description": "要替换的原始内容，必须在文件中唯一存在",
                    },
                    "new_str": {
                        "type": "string",
                        "description": "替换后的新内容",
                    },
                },
                "required": ["path", "old_str", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_file",
            "description": "在文件中搜索指定内容，返回匹配的行号和内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要搜索的文件路径",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "要搜索的内容（字符串，非正则）",
                    },
                },
                "required": ["path", "pattern"],
            },
        },
    },
]
