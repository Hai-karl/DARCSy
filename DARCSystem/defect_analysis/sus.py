"""System Usability Scale (Brooke, 1996): 10 items answered 1-5."""


def sus_score(answers) -> float:
    if not isinstance(answers, (list, tuple)) or len(answers) != 10 or \
            any(not isinstance(a, int) or isinstance(a, bool) or not 1 <= a <= 5 for a in answers):
        raise ValueError("Answer all 10 statements with a number from 1 to 5.")
    odd = sum(a - 1 for a in answers[0::2])       # items 1,3,5,7,9: positive wording
    even = sum(5 - a for a in answers[1::2])      # items 2,4,6,8,10: negative wording
    return (odd + even) * 2.5


def sus_verdict(score: float) -> str:
    return "above the usual average of 68" if score >= 68 else "below the usual average of 68"
