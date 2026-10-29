"""Measure chatbot accuracy.

    python evaluate.py               # held-out test set + cross-validation
    python evaluate.py --tune        # also try several confidence thresholds
"""
import argparse
import json
from collections import Counter

from sklearn.model_selection import StratifiedKFold, cross_val_score

from legacy.bot_v1 import DATA_DIR, ChatBot, build_model, load_intents, normalize


def held_out_accuracy(bot, samples, verbose=True):
    correct, misses = 0, []
    for text, expected in samples:
        got, conf = bot.classify(text)
        if got == expected:
            correct += 1
        else:
            misses.append((text, expected, got, conf))
    if verbose:
        for text, expected, got, conf in misses:
            print(f"  ✘ {text!r}: expected {expected}, got {got} ({conf:.2f})")
    return correct / len(samples)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tune", action="store_true")
    args = parser.parse_args()

    intents = load_intents()
    with open(DATA_DIR / "test_set.json", encoding="utf-8") as f:
        samples = json.load(f)["samples"]

    texts = [normalize(p) for i in intents["intents"] for p in i["patterns"]]
    labels = [i["tag"] for i in intents["intents"] for _ in i["patterns"]]
    folds = min(5, min(Counter(labels).values()))
    cv = cross_val_score(build_model(), texts, labels,
                         cv=StratifiedKFold(folds, shuffle=True, random_state=0))
    print(f"Intents: {len(intents['intents'])}, training patterns: {len(texts)}")
    print(f"{folds}-fold cross-validation accuracy: {cv.mean():.1%} (±{cv.std():.1%})")

    bot = ChatBot(intents)
    print(f"\nHeld-out test set ({len(samples)} unseen messages, threshold={bot.threshold}):")
    acc = held_out_accuracy(bot, samples)
    print(f"Accuracy: {acc:.1%}")

    if args.tune:
        print("\nThreshold tuning:")
        for t in (0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4):
            bot.threshold = t
            print(f"  threshold {t:.2f}: {held_out_accuracy(bot, samples, verbose=False):.1%}")


if __name__ == "__main__":
    main()
