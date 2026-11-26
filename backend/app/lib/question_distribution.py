ORDER = ("LU", "CU", "AU", "CT")


def distribute(total, selected):
    if type(total) is not int or not 1 <= total <= 25:
        raise ValueError("Total must be a whole number from 1 to 25.")
    if not selected or len(set(selected)) != len(selected) or any(c not in ORDER for c in selected):
        raise ValueError("Select one or more distinct competencies.")
    codes = [c for c in ORDER if c in selected]
    base, remainder = divmod(total, len(codes))
    return {c: base + (codes.index(c) < remainder) if c in codes else 0 for c in ORDER}
