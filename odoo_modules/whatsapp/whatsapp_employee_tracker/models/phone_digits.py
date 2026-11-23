"""Two phone numbers compared by their digits (23 Nov 2026)."""


def digits(text):
    return ''.join(c for c in (text or '') if c.isdigit())


def same_number(one, two):
    one, two = digits(one), digits(two)
    return bool(one and two) and (one == two or (min(len(one), len(two)) >= 9 and one[-9:] == two[-9:]))
