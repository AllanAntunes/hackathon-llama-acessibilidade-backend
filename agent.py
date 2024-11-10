from flask import request
import requests
import json
import os

MODEL="llama-3.2-90b-vision-preview"

def pegar_info(team_name):
    headers = {'Authorization': request.headers.get('Authorization')}
    response = requests.get("https://api.acessibilidade.tec.br/space", headers=headers)
    return response.text

def run_conversation(user_prompt, groq_client):
    messages=[
        {
            "role": "system",
            "content": """Você é o Curador.ia, uma IA que fornece informações sobre exposições de arte e responde as perguntas que venham no texto.
            O texto será extraído de um áudio, portanto pode haver erros, mesmo assim tente ser informativo enquanto formula a resposta.
            Use a função pegar_info para receber informações relevantes sobre as exposições. Sua resposta será transformada em áudio, então faça parecer como uma conversa.
            É importante ter como resposta somente o que vai pro áudio, não tenha introduções, a não ser que o usuário diga.
                        """
        },
        {
            "role": "user",
            "content": user_prompt,
        }
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "pegar_info",
                "description": "Retorna as descrições das exposições",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "exibition_name": {
                            "type": "string",
                            "description": "The name of the art",
                        }
                    },
                    "required": ["exibition_name"],
                },
            },
        }
    ]

    response = groq_client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        max_tokens=4096,
        temperature=0
    )

    response_message = response.choices[0].message

    tool_calls = response_message.tool_calls

    if tool_calls:
        available_functions = {
            "pegar_info": pegar_info,
        }

        messages.append(response_message)

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_to_call = available_functions[function_name]
            function_args = json.loads(tool_call.function.arguments)
            function_response = function_to_call(
                team_name=function_args.get("team_name")
            )
            messages.append(
                {
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                }
            )

        second_response = groq_client.chat.completions.create(
            model=MODEL,
            messages=messages
        )
        return second_response.choices[0].message.content
    else:
        return response.choices[0].message.content