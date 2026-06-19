from abc import ABC, abstractmethod
from dataclasses import dataclass


class NoteContent(ABC):
    @abstractmethod
    def to_dict(self) -> dict: ...

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict): ...


@dataclass
class PlainTextContent(NoteContent):
    body: str = ""

    def to_dict(self) -> dict:
        return {"body": self.body}

    @classmethod
    def from_dict(cls, data: dict):
        return cls(body=data.get("body", ""))


CONTENT_REGISTRY: dict[str, type[NoteContent]] = {
    "plain_text": PlainTextContent,
}


def content_from_dict(template_type: str, data: dict) -> NoteContent:
    cls = CONTENT_REGISTRY.get(template_type, PlainTextContent)
    return cls.from_dict(data)
