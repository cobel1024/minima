import asyncio
from typing import AsyncIterator

from google import genai
from google.genai import types

from apps.assistant.agent.base import BaseAgent


class GeminiAgent(BaseAgent):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-2.5-flash-lite"
        self.temperature = 1.0

    async def generate_stream(
        self,
        message: str,
        context: list[dict] | None = None,
        system_instruction: str | None = None,
        parts: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        contents: list[types.ContentUnion] = []

        if context:
            for msg in context:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

        message_parts = []

        if parts:
            for part in parts:
                uploaded_file = await self.client.aio.files.upload(
                    file=part["file"],
                    config=types.UploadFileConfig(mime_type=part["mime_type"], display_name=part.get("filename")),
                )

                if not uploaded_file.name:
                    raise ValueError("File upload failed: no file name returned")

                while uploaded_file.state and uploaded_file.state.name == "PROCESSING":
                    await asyncio.sleep(1)
                    uploaded_file = await self.client.aio.files.get(name=uploaded_file.name)

                if uploaded_file.state and uploaded_file.state.name == "FAILED":
                    raise ValueError(f"File upload failed: {uploaded_file.name}")

                message_parts.append(
                    types.Part(file_data=types.FileData(file_uri=uploaded_file.uri, mime_type=uploaded_file.mime_type))
                )

        message_parts.append(types.Part(text=message))
        contents.append(types.Content(role="user", parts=message_parts))

        config = types.GenerateContentConfig(system_instruction=system_instruction, temperature=self.temperature)
        stream = await self.client.aio.models.generate_content_stream(
            model=self.model, contents=contents, config=config
        )

        async for chunk in stream:
            if chunk.text:
                yield chunk.text
