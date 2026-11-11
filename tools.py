
READ_TOOL = {
    "type" : "function",
    "function" : {
        "name" : "read_file",
        "description" : "Read a file in the workspace",
        "parameters" : {
            "type" : "object",
            "properties" : {"file_name" : {"type" : "string"}},
            "required" : ["file_name"]
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
            "properties" : {},
            "required" : []
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
                "required" : ["flie_name", "text"]
            }
        }
}

SHELL_TOOL = {
    "type" : "function",
        "function" : {
            "name" : "run_shell",
            "description" : "Run a shell command in workplace and return its output",
            "parameters" : {
                "type" : "object",
                "properties" : {
                    "command" : {"type":"string"}
                },
                "required" : ["command"]
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
                "required" : ["file_name", "old", "new"]
            }
        }
}
