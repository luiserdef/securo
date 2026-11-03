import base64
import quopri
import re
import json
import httpx
import logging
from bs4 import BeautifulSoup
from datetime import datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime,date
from email.utils import parsedate_to_datetime
from app.core.config import get_settings

from app.agents.providers.ollama import OllamaProvider
from app.agents.providers.base import (
    ChatChunk,
    ChatMessage,
)

import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from google.auth.exceptions import RefreshError
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)


SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
LABEL_UNPROCESSED = "securonoprocesado"
LABEL_PROCESSED = "securoprocesado"

systemPrompt = """Eres un extractor de datos financieros. Recibirás el texto plano de una notificación bancaria o de una tarjeta de crédito/débito (SMS, correo o push).

Devuelve ÚNICAMENTE un objeto JSON válido, sin explicaciones, texto adicional ni bloques de código.

Estructura exacta:

{
"date": "<string ISO 8601 o "">",
"description": "<string>",
"amount": <number>,
"type": "<debit o credit>",
"note": "<string o "">"
}

REGLAS:

1. IDENTIFICACIÓN DE TITULAR Y CONTRAPARTE

* Si el texto comienza con un saludo como "Hola, <Nombre>:", ese nombre es el TITULAR de la cuenta. Nunca lo consideres como la contraparte de la transacción.
* La CONTRAPARTE es la persona, empresa o comercio directamente relacionado con la transacción.
* Ejemplos:

  * "<Empresa> te envió..." → contraparte = Empresa
  * "Pago a <Comercio>" → contraparte = Comercio
  * "Compra en <Comercio>" → contraparte = Comercio
  * "Enviado a <Persona>" → contraparte = Persona
  * "Enviado por <Persona>" → contraparte = Persona
  * "Pagado a <Comercio>" → contraparte = Comercio
* La descripción debe utilizar la CONTRAPARTE, nunca el nombre del titular.

2. DATE

* Extrae la fecha y hora de la transacción, no la fecha de envío del correo si son diferentes.
* Convierte fechas como "YYYY/MM/DD-HH:MM:SS" a ISO 8601:
  "YYYY-MM-DDTHH:MM:SS".
* Si el texto proporciona una zona horaria, inclúyela.
* Si la zona horaria puede determinarse razonablemente por el contexto, inclúyela.
* Si no puede determinarse, no inventes una zona horaria.
* Si no existe fecha, devuelve null.

3. DESCRIPTION

La descripción debe ser corta, clara.

Prioridad:
* "Enviaste por" siempre significa que ENTREGASTE dinero, aunque posteriormente aparezca la frase "Enviado a".
    - Ejemplo Entrada:
        "Enviaste por LCN\n$5.00\nEnviado\na\nCoyote\nCastro"
    Salida:
        "LCN send to Coyote Castro" 
* "Te enviaron por" siempre significa que RECIBISTE dinero, aunque posteriormente aparezca la frase "Enviado por".
    - Ejemplo Entrada:
        "Te enviaron por LCN\n$2.96\nEnviado\npor\nAvestruz\nMelasco"
    Salida:
        "LCN from Avestruz Melasco"
* "Pagaste por" siempre significa que ENTREGASTE dinero, aunque posteriormente aparezca la frase "Pagado a".
    - Ejemplo Entrada:
        "Pagaste por LCN\n$2.96\nPagado a\nACME"
    Salida:
        "LCN send to ACME"        
* Nunca determines el movimiento únicamente por la palabra "Enviado". Debes considerar la frase completa y su contexto.

* Si es una compra o pago:
  incluir el nombre del comercio.
* Si es una transferencia:
  incluir la contraparte.
* No incluyas el método de pago en la descripción.
* Normaliza nombres de comercios para hacerlos legibles. Por ejemplo:
  "GOOGLE*LIGHTROOM PHOT" → "Google Lightroom Photo".

4. AMOUNT

* Extrae el monto de la transacción.
* Ignora símbolos y códigos de moneda como $, US$, USD, ₡, etc.
* Devuelve siempre un número usando punto como separador decimal.
* Si no se encuentra el monto, devuelve 0.

5. TYPE

* "Te enviaron por" → "credit"
* "Enviaste por" → "debit"
* "Pagado a" → "debit"
* Si recibo, deposito o me transfieren dinero → "credit"
* Si pago, compro, retiro o envío dinero → "debit"
* Si existe suficiente información, siempre intenta determinar el tipo o movimiento.

6. NOTE

Incluye únicamente información adicional relevante para entender la transacción, por ejemplo:

* Incluye siempre la palabra #SYNC y luego incluye despues de un salto de linea la informacion si cumple con los criterior mencionados abajo.
* tipo de compra: "Internet"
* estado: "Aprobada"
* canal: "online", "presencial", "cajero"
* banco emisor
* número de confirmación
* mensaje asociado a la transferencia

No incluyas:

* nombre del titular
* enlaces de ayuda
* redes sociales
* números de WhatsApp
* avisos legales
* disclaimers
* firmas
* pies de correo
* Informacion para mas detalles
* información que no esté relacionada con la transacción

Si no existe información adicional relevante, devuelve null.

REGLAS GENERALES

* No inventes datos.
* Usa null cuando un campo de texto no pueda determinarse.
* "amount" debe ser 0 si no se encuentra.
* "movement" debe inferirse siempre que sea razonablemente posible.
* La salida debe ser JSON válido y parseable.
* No agregues texto antes o después del JSON.

EJEMPLO 1:

TEXTO:
Hola, mark:\r\n\r\nACME, S.A. te envió la siguiente transacción:\r\n\r\nA tu: CUENTA DE AHORROS\r\nTerminación de producto: 5965\r\nMonto: US$25.00\r\n\r\n Para más detalles, consulta los movimientos de tu CUENTA DE AHORROS en BANCA EN LINEA.\r\n

SALIDA:
{
"date": "",
"description": "ACME, S.A. Transaction",
"amount": 25.00,
"type": "credit",
"note": "#SYNC"
}

EJEMPLO 2:

TEXTO:
Enviaste por LCN\n$7.77\nEnviado\na\nCoyote\nVentura\n64481770\nFecha\n25 jun 2023 02:29 p.\xa0m.\nMensaje\npago de casa madera\nConfirmación\nKNKSC-35246173

SALIDA:
{
"date": "2023-06-25T14:29:00-06:00",
"description": "LCN send to Coyote Ventura",
"amount": 7.77,
"type": "debit",
"note": "#SYNC\npago de casa madera. Confirmación KNKSC-35246173"
}

EJEMPLO 3:

TEXTO:
Te enviaron por LCN\n$13.00\nEnviado\npor\nBug\nBunny\n1112222\nFecha\n02 sept 2025 01:50 p.\xa0m.\nMensaje\nConfirmación\nEUYAK-79320984

SALIDA:
{
"date": "2025-09-02T13:50:00-06:00",
"description": "LCN from Bug Bunny",
"amount": 13.00,
"type": "credit",
"note": "#SYNC\nConfirmation EUYAK-79320984"
}

EJEMPLO 4:

TEXTO:
 Logo LCN \t\r\nEstimado/a: Steve \r\n\r\nSe acaba de realizar una compra con tu tarjeta terminada en 0000 \r\n\r\nDetalles del movimiento: \r\n\r\n \t \t\r\nComercio \r\n\r\nMonto \r\n\r\nVice City world 1094 \r\n\r\nUSD 7.04 \r\n\r\n \t\r\nFecha y hora \r\n\r\n2022/09/12-17:38:24 \r\n\r\n \t \t\r\nTipo de compra \r\n\r\nEstado \r\n\r\nTarjeta Presente \r\n\r\nAprobada

SALIDA:
{
"date": "2022-09-12T17:38:24-06:00",
"description": "Vice City World Transaction",
"amount": 7.04,
"type": "debit",
"note": "#SYNC\nStatus: Aproved"
}

EJEMPLO 5:

TEXTO:
Tu recarga de carro por US$1.00 realizada por BANCA MOVIL fue REALIZADA.

SALIDA:
{
"date": "",
"description": "recarga de carro",
"amount": 1.00,
"type": "debit",
"note": "#SYNC"
}

EJEMPLO 6:

TEXTO:
Pagaste por LCN $1.60 Pagado a ACME Fecha 1 febr 2026 00:01 a.m. Mensaje Por pedido 3333 Confirmación PPPPP-9999

SALIDA:
{
"date": "2026-02-01T17:00:01-06:00",
"description": "LCN send to ACME",
"amount": 1.60,
"type": "debit",
"note": "#SYNC\nPor pedido 3333\nConfirmation PPPPP-9999"
}


A continuación el texto:

"""

def model_response(texto: str, model: str = "gemma3:4b") -> dict:
    """
    Envía 'texto' a Ollama (modelo local) y devuelve la respuesta como string.
    """
    # url = "http://localhost:11434/api/chat"
    url = "http://host.docker.internal:11434/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": systemPrompt},
            {"role": "user", "content": texto}],
        "stream": True,
        "think": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": 300},
    }
 
    response = ""
 
    try:
        with httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
            with client.stream("POST", url, json=payload) as resp:
                if resp.status_code >= 400:
                    body = resp.read().decode("utf-8", errors="replace")
                    raise RuntimeError(f"Ollama {resp.status_code}: {body}")
 
                for line in resp.iter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    contenido = (data.get("message") or {}).get("content") or ""
                    response += contenido
                    if data.get("done"):
                        break
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Ollama unreachable: {exc}") from exc
 
    return json.loads(response)


def build_flow() -> Flow:
    settings = get_settings()
    creds = json.loads(settings.google_client_creds.get_secret_value())

    client_key = "web" if "web" in creds else "installed"
    redirect_uri = creds[client_key]["redirect_uris"][0]

    flow = Flow.from_client_config(
        creds,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    flow.autogenerate_code_verifier = False
    return flow

class AuthError(Exception):
    """Error for authentication"""

class GmailAuth():

    def exchange_code(self, code: str) -> Credentials:
        flow = build_flow()
        flow.fetch_token(code=code)
        return flow.credentials

    def get_valid_credentials(self, token_info: dict | None) -> tuple[Credentials | None, bool]:
            """
            Intenta conseguir credenciales válidas.
            Devuelve (creds, refreshed):
            - (creds, False) -> ya eran válidas
            - (creds, True)  -> estaban expiradas y se refrescaron
            - (None, False)  -> no se pudo, hay que re-autenticar
            """
            if not token_info:
                return None, False

            try:
                creds = Credentials.from_authorized_user_info(token_info, SCOPES)
            except (ValueError, KeyError) as e:
                logger.warning("Credenciales ilegibles: %s", e)
                return None, False

            if creds.valid:
                return creds, False

            if creds.refresh_token:
                try:
                    creds.refresh(Request())
                    return creds, True
                except RefreshError as e:
                    detalle = e.args[1] if len(e.args) > 1 and isinstance(e.args[1], dict) else {}
                    # raise ValueError(detalle.get("error_description"))
                    logger.warning("Failed Refresh: %s", detalle.get("error_description"))

            return None, False

    def get_auth_url(self,state:str) -> str:
        flow = build_flow()
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            state = state,
        )
        return auth_url

    @staticmethod
    def to_dict(creds: Credentials) -> dict:
        return json.loads(creds.to_json())

class GmailMessagesData:
    def __init__(self, token_info_creds:str):

        try:
            token_info = json.loads(token_info_creds)
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            raise ValueError("Credenciales inválidas") from e

        if creds and creds.valid:
            self.service = build("gmail", "v1", credentials=creds)
        else:
            self.service = None  
            raise ValueError("No credentials found") 

        email_labels = []
        self.loadLabels() 

    def loadLabels(self):
        request = self.service.users().labels().list(userId="me")
        result = self._execute_request(request)
        self.email_labels = result.get("labels", [])

    def getLabelId(self, label_name):
        for label in self.email_labels:
            if label_name.lower() == label["name"].lower():
                return label["id"]                 
        return None
 
    def removeLabel(self, labelId, message_id):
        request = (
            self.service.users()
            .messages()
            .modify(userId="me", id=message_id, body={"removeLabelIds":[labelId]})
        )
        result = self._execute_request(request)

        if not result:
            return None

    def addLabel(self, labelId, message_id):
        request = (
            self.service.users()
            .messages()
            .modify(userId="me", id=message_id, body={"addLabelIds":[labelId]})
        )
        result = self._execute_request(request)

        if not result:
            return None            

    def updateEmailLabel(self,message_id):
        processed = self.getLabelId(LABEL_PROCESSED)
        unprocessed = self.getLabelId(LABEL_UNPROCESSED)

        try:
            self.addLabel(processed,message_id)
            self.removeLabel(unprocessed,message_id)
        except Exception as e:
            raise ValueError({e})


    def find_emails(self, labelId):
        request = (
            self.service.users()
            .messages()
            .list(userId="me", labelIds=labelId)
        )
        result = self._execute_request(request)

        if result["resultSizeEstimate"] == 0:
             return None

        return result["messages"]      

    def get_email(self, email_id: str):
        request = self.service.users().messages().get(userId="me", id=email_id, format="full")
        result = self._execute_request(request)
        return result

    @staticmethod
    def _decode(data):
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    @staticmethod
    def _execute_request(request):
        try:
            return request.execute()
        except HttpError as e:
            print(f"An error occurred: {e}")
            raise RuntimeError(e)

    def get_email_summary(self) -> dict:
        target_label_Id = self.getLabelId(LABEL_UNPROCESSED)
        if not target_label_Id:
            raise ValueError("No email found with target Label.")  

        summary = []
        emails = self.find_emails(target_label_Id)
        
        if not emails:
            return None 

        for email in emails:
            message = self.get_email(email["id"])
            payload = message["payload"]
            headers = payload["headers"]

            payload_raw = self.get_body(payload)

            if payload_raw.get("plain"):
                email_message = payload_raw["plain"]
            elif payload_raw.get("html"):
                email_message = self.html_to_text(payload_raw["html"])
            else:
                email_message = None

            summary.append({
                "email_id": email["id"],
                "subject": self._get_header(headers, "Subject"),
                "sender": self._get_header(headers, "From"),
                "date": self.clean_date(self._get_header(headers, "Date")),
                "raw_message": email_message,
            })

        return summary

    @staticmethod 
    def extract_transaction_data(text:str)-> dict:
        return model_response(text)
    
    @staticmethod  
    def clean_date(value):
        value = re.sub(r"\s*\([^)]*\)", "", value)
        return datetime.strptime(value, "%a, %d %b %Y %H:%M:%S %z").date()
    

    def get_body(self, payload):
        body_data = {"plain": None, "html": None}

        def decode_base64(data):
            data = data.replace("-", "+").replace("_", "/")
            padding = 4 - (len(data) % 4)
            if padding != 4:
                data += "=" * padding
            return base64.b64decode(data)

        def get_transfer_encoding(part):
            headers = part.get("headers", [])
            for h in headers:
                if h.get("name", "").lower() == "content-transfer-encoding":
                    return h.get("value", "").lower()
            return None

        def walk(part):
            mime_type = part.get("mimeType", "")
            body = part.get("body", {})

            if body.get("data"):
                raw_bytes = decode_base64(body["data"])

                encoding = get_transfer_encoding(part)
                if encoding == "quoted-printable":
                    raw_bytes = quopri.decodestring(raw_bytes)

                texto = raw_bytes.decode("utf-8", errors="replace")

                if mime_type == "text/plain":
                    body_data["plain"] = texto
                elif mime_type == "text/html":
                    body_data["html"] = texto

            for sub_part in part.get("parts", []):
                walk(sub_part)

        walk(payload)
        return body_data

    def html_to_text(self, html: str) -> str:
        """Convierte HTML a texto plano legible, quitando tags, scripts y estilos."""
        soup = BeautifulSoup(html, "html.parser")

        # Quitar elementos que no aportan texto útil
        for tag in soup(["script", "style"]):
            tag.decompose()

        texto = soup.get_text(separator="\n")

        # Limpiar líneas vacías/espacios sobrantes
        lineas = [line.strip() for line in texto.splitlines()]
        lineas = [line for line in lineas if line]
        return "\n".join(lineas)

    def _get_header(self, headers: list[dict], name: str) -> str | None:  # <-- fix: self
        for h in headers:
            if h["name"].lower() == name.lower():
                return h["value"]
        return None