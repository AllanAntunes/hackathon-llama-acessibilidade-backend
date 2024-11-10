from flask import request
import requests
import json
import os

class agent:
    def __init__(self,space_id):
        self.__MODEL="llama-3.2-90b-vision-preview"
        self.__space_id = space_id
        self.__space_item_id : str

    def __pegar_info_expo(self):
        headers = {'Authorization': request.headers.get('Authorization')}
        response = requests.get(f"https://api.acessibilidade.tec.br/space/{self.__space_id}", headers=headers)
        return response.text

    def __pegar_info_item(self):
        headers = {'Authorization': request.headers.get('Authorization')}
        response = requests.get(f"https://api.acessibilidade.tec.br/space/{self.__space_id}/item/", headers=headers)
        return response.text
    
    def run_conversation(self, user_prompt, groq_client):
        
        messages=[
            {
                "role": "system",
                "content": """Você é o Curador.ia, uma IA que fornece informações sobre exposições de arte e responde as perguntas que venham no texto.
                O texto será extraído de um áudio, portanto pode haver erros, mesmo assim tente ser informativo enquanto formula a resposta.
                Use a função __pegar_info_expo para receber informações relevantes sobre as exposições.
                Use a função __pegar_info_item para receber as informações sobre os itens da exposição.
                Sua resposta será transformada em áudio, então faça parecer como uma conversa.
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
                    "name": "__pegar_info_expo",
                    "description": "Retorna a descrição das exposição",
                },
            },
                        {
                "type": "function",
                "function": {
                    "name": "__pegar_info_item",
                    "description": "Retorna a descrição dos itens da exposição",
                },
            }
        ]

        response = groq_client.chat.completions.create(
            model=self.__MODEL,
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
                "__pegar_info_expo": self.__pegar_info_expo,
                "__pegar_info_item": self.__pegar_info_item
            }

            messages.append(response_message)

            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_to_call = available_functions[function_name]
                messages.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                    }
                )

            second_response = groq_client.chat.completions.create(
                model=self.__MODEL,
                messages=messages
            )
            return second_response.choices[0].message.content
        else:
            return response.choices[0].message.content