
READ_TOOL = {
    "type" : "function",
    "function" : {
        "name" : "read_file",
        "description" : "Read a file in the workspace",
        "parameters" : {
            "type" : "object",
            "properties" : {"file_name" : {"type" : "string"}},
            "required" : ["file_name"],
            "additionalProperties":False
        }
    }
}

LIST_TOOL = {
    "type" : "function",
    "function" : {
        "name" : "list_dir",
        "description" : "List all the files present in the workspace",
        "parameters" : {
            "type" : "object",
            "properties" : {"path" : {"type" : "string", "description": "Directory path relative to workspace (use \".\" for root)"}},
            "required" : ["path"],
            "additionalProperties": False
        }
    }
}

WRITE_TOOL = {
    "type" : "function",
        "function" : {
            "name" : "write_file",
            "description" : "Write to a new file",
            "parameters" : {
                "type" : "object",
                "properties" : {"file_name" :{"type" : "string"}, "text" : {"type" : "string"}},
                "required" : ["file_name", "text"],
                "additionalProperties" : False
            }
        }
}

SHELL_TOOL = {
    "type" : "function",
        "function" : {
            "name" : "run_shell",
            "description" : "Run a shell command in workspace and return its output",
            "parameters" : {
                "type" : "object",
                "properties" : {
                    "command" : {"type":"string"}
                },
                "required" : ["command"],
                "additionalProperties" : False
            }
        }
}

EDIT_TOOL = {
    "type" : "function",
        "function" : {
            "name" : "edit_file",
            "description" : "Edit an already existing file. Use the fewest lines that match exactly once, usually 1 to 5. Never paste the whole file. To add code at the end, use the last line of the file as old and include it again in new, followed by the new code",
            "parameters" : {
                "type" : "object",
                "properties" : {
                    "file_name" : {"type" : "string"},
                    "old" : {"type":"string"},
                    "new" : {"type" : "string"}
                },
                "required" : ["file_name", "old", "new"],
                "additionalProperties" : False
            }
        }
}

TODO_TOOL = {
    "type" : "function",
    "function" : {
        "name" : "todo_write",
        "description": (
            "Plan and track multi-step work. Replaces the whole list each time, so "
            "include every item. Keep exactly one item in_progress while work remains. "
            "Mark an item completed only after the work and its check are done. "
            "Do not use for a single trivial step."
        ),
        "parameters": {
  "type": "object",
  "properties": {
    "todos": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "content": {"type": "string"},
          "status": {
            "type": "string",
            "enum": ["pending", "in_progress", "completed", "cancelled"]
          }
        },
        "required": ["content", "status"],
        "additionalProperties": False
      }
    }
  },
  "required": ["todos"],
  "additionalProperties": False
}
}}
