"""Shared 2D vector geometry utilities for pursuit / navigation / relay environments."""

from __future__ import annotations

import math

__all__ = ["Vec2", "add", "sub", "mul", "norm", "unit", "clamp", "distance", "rotate"]

Vec2 = tuple[float, float]

def add(a: Vec2, b: Vec2) -> Vec2:
    return (a[0] + b[0], a[1] + b[1])

def sub(a: Vec2, b: Vec2) -> Vec2:
    return (a[0] - b[0], a[1] - b[1])

def mul(a: Vec2, scale: float) -> Vec2:
    return (a[0] * scale, a[1] * scale)

def norm(a: Vec2) -> float:
    return math.hypot(a[0], a[1])

def unit(a: Vec2) -> Vec2:
    length = norm(a)
    if length < 1e-9:
        return (1.0, 0.0)
    return (a[0] / length, a[1] / length)

def clamp(a: Vec2, max_norm: float) -> Vec2:
    length = norm(a)
    if length <= max_norm or length < 1e-9:
        return a
    return mul(a, max_norm / length)

def distance(a: Vec2, b: Vec2) -> float:
    return norm(sub(a, b))

def rotate(a: Vec2, radians: float) -> Vec2:
    c = math.cos(radians)
    s = math.sin(radians)
    return (a[0] * c - a[1] * s, a[0] * s + a[1] * c)