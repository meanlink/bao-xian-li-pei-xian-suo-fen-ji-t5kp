import math

class LogisticRegression:
    """可复现的二元逻辑回归，使用小规模固定样本和梯度下降。"""
    def __init__(self, learning_rate=0.25, epochs=650):
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.weights = []

    @staticmethod
    def sigmoid(value):
        value = max(-35.0, min(35.0, value))
        return 1.0 / (1.0 + math.exp(-value))

    def fit(self, x, y):
        self.weights = [0.0] * (len(x[0]) + 1)
        for _ in range(self.epochs):
            gradients = [0.0] * len(self.weights)
            for row, target in zip(x, y):
                z = self.weights[0] + sum(w * f for w, f in zip(self.weights[1:], row))
                error = self.sigmoid(z) - target
                gradients[0] += error
                for index, feature in enumerate(row, 1):
                    gradients[index] += error * feature
            for index in range(len(self.weights)):
                self.weights[index] -= self.learning_rate * gradients[index] / len(x)
        return self

    def predict_proba(self, row):
        return self.sigmoid(self.weights[0] + sum(w * f for w, f in zip(self.weights[1:], row)))

TRAIN_X = [
    [0.05, 0.10, 0.10, 0.10], [0.20, 0.15, 0.10, 0.15], [0.12, 0.25, 0.20, 0.18],
    [0.35, 0.30, 0.40, 0.32], [0.45, 0.42, 0.50, 0.46], [0.55, 0.48, 0.60, 0.58],
    [0.68, 0.62, 0.70, 0.72], [0.75, 0.70, 0.80, 0.78], [0.86, 0.82, 0.88, 0.90],
    [0.92, 0.90, 0.95, 0.94],
]
TRAIN_Y = [0, 0, 0, 0, 1, 1, 1, 1, 1, 1]

MODEL = LogisticRegression().fit(TRAIN_X, TRAIN_Y)

def claim_features(claim: dict, clues: list[dict]):
    amount = min(float(claim["loss_amount"]) / 200000.0, 1.0)
    incident = {"盗抢": 0.80, "车损": 0.35, "医疗": 0.42, "水灾": 0.58, "火灾": 0.68}.get(claim["incident_type"], 0.30)
    region = {"沿海": 0.72, "都市": 0.48, "山区": 0.35, "园区": 0.40}.get(claim["region"], 0.30)
    clue_signal = min(sum({"low": 0.08, "medium": 0.20, "high": 0.35}.get(c["severity"], 0.0) for c in clues), 1.0)
    return [amount, incident, region, clue_signal]

def score_claim(claim: dict, clues: list[dict]):
    features = claim_features(claim, clues)
    return MODEL.predict_proba(features), features

def confusion_matrix(records: list[tuple[float, bool]], threshold: float):
    tp = tn = fp = fn = 0
    for score, actual in records:
        predicted = score >= threshold
        if predicted and actual: tp += 1
        elif predicted and not actual: fp += 1
        elif not predicted and actual: fn += 1
        else: tn += 1
    total_negative = fp + tn
    fpr = fp / total_negative if total_negative else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn, "false_positive_rate": round(fpr, 4), "recall": round(recall, 4), "precision": round(precision, 4)}

def choose_threshold(records: list[tuple[float, bool]], max_fpr: float):
    candidates = [round(x / 100, 2) for x in range(20, 91, 5)]
    evaluated = [(threshold, confusion_matrix(records, threshold)) for threshold in candidates]
    valid = [(threshold, metrics) for threshold, metrics in evaluated if metrics["false_positive_rate"] <= max_fpr]
    if valid:
        return max(valid, key=lambda item: (item[1]["recall"], item[1]["precision"], item[0]))
    return min(evaluated, key=lambda item: item[1]["false_positive_rate"])
