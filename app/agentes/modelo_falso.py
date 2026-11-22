"""Modelo del Agents SDK que sigue un guion fijo sin conectar a un proveedor."""
import json

from agents import Model, ModelResponse, Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText


class ModeloFalso(Model):
    def __init__(self, herramienta: str = "buscar_documentacion", argumentos: dict | None = None):
        self.herramienta = herramienta
        self.argumentos = argumentos

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing,
                           *, previous_response_id, conversation_id, prompt):
        elementos = input if isinstance(input, list) else [{"role": "user", "content": input}]
        resultado = next((item["output"] for item in reversed(elementos)
                          if item.get("type") == "function_call_output"), None)
        if resultado is None:
            pregunta = next((item["content"] for item in reversed(elementos) if item.get("role") == "user"), "")
            args = self.argumentos if self.argumentos is not None else {"consulta": pregunta}
            salida = ResponseFunctionToolCall(
                type="function_call", call_id="call_guion_documentador", name=self.herramienta,
                arguments=json.dumps(args, ensure_ascii=False),
            )
        else:
            if isinstance(resultado, list):
                resultado = "".join(item.get("text", "") for item in resultado)
            fuentes = json.loads(resultado).get("fuentes", [])
            respuesta = ("No lo encontré en la documentación." if not fuentes else fuentes[0]["texto"])
            datos = {"respuesta": respuesta, "fuentes": [fuentes[0]["id"]] if fuentes else []}
            salida = ResponseOutputMessage(
                id="msg_guion_documentador", role="assistant", status="completed", type="message",
                content=[ResponseOutputText(type="output_text", text=json.dumps(datos, ensure_ascii=False), annotations=[])],
            )
        return ModelResponse(output=[salida], usage=Usage(requests=1, input_tokens=12, output_tokens=6, total_tokens=18),
                             response_id=None)

    def stream_response(self, *args, **kwargs):
        raise NotImplementedError("El modelo de prueba ejecuta el guion sin streaming")
