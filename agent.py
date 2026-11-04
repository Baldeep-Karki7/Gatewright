import logging
import os
import sys
import traceback

import openai
from dotenv import load_dotenv
from openai import OpenAI

from llm import call_llm
from utils import (
    change_report,
    edit_file,
    initialize_git,
    list_dir,
    load_history,
    read_file,
    run_shell,
    save_history,
    snapshot,
    trim_messages,
    write_file,
)

#root logger config
logging.basicConfig(
    filename='agent.log',
    level = logging.INFO,
    format = "%(asctime)s %(levelname)s %(message)s")

#get a module level logger with .getLogger(__name__)
logger = logging.getLogger(__name__)

load_dotenv()
client = OpenAI(base_url="https://ollama.com/v1",
                api_key=os.environ["OLLAMA_API_KEY"],
                max_retries=4,
                timeout=120.0)


available_functions = {"read_file" : read_file, "list_dir" : list_dir, "write_file": write_file, "run_shell" : run_shell, "edit_file" : edit_file}


if __name__ == "__main__" :

    #load the history
    messages = load_history()

    #ensure the repo is git initialized
    reporting_enabled = initialize_git()
    if not reporting_enabled:
        print("IMPORTANT : Git must be installed. Cannot observe file changes without git")
        sys.exit(1)

    #trim the list
    messages = trim_messages(messages, max_messages = 10)
    while True:
        try:
            user_input = input("User : ")
        except (EOFError, KeyboardInterrupt):
            break 

        checkpoint = len(messages)
        messages.append({"role" : "user", "content" : user_input})

        #before each call_llm take before snapshot of work tree
        before = snapshot()
        logger.info('CHANGES hash = %s', before)

        try:
            reply = call_llm(client, messages, available_functions)
            messages.append({"role":"assistant", "content" : reply})
            #after each return of the chat, save the history
            save_history(messages= messages)
            print(f"Assistant : {reply}")

        except openai.AuthenticationError:
            logger.exception("Auth failed")
            print('API key rejected. Check Ollama API key')
            del messages[checkpoint:]
        except openai.RateLimitError:
            logger.exception("Max retries reached ")
            print("Too many requests. Wait a minute and retry")
            del messages[checkpoint:]
        except (openai.APIConnectionError, openai.APITimeoutError):
            print("Network failure after retries")
            logger.exception("Couldnot reach the API. Check the connection and try again")
            del messages[checkpoint:]
        except Exception as e:
            print(f'error : {e}')  
            logger.exception("turn failed")
            traceback.print_exc()
            del messages[checkpoint:]
        finally:
            after = snapshot() 
            logger.info('CHANGES hash = %s', after)
            print(before, after)
            if after is not None and after !=before:
                report = change_report(before, after)
                print(report)


