from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    x: int
    y: int

    def __add__(self, other: "Position") -> "Position":
        return Position(self.x + other.x, self.y + other.y)

    def __repr__(self) -> str:
        return f"({self.x}, {self.y})"
