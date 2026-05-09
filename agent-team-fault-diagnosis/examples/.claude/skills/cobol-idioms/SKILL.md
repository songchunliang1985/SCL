---
name: COBOL→Java 変換コード読解
description: COBOL から Java へ変換されたコードに残る非 idiomatic パターン（COMP-3、copybook、固定長、レベル番号、PERFORM 風フロー、フラグ駆動、巨大メソッド）の理解を支援。backend-analyzer, mq-inspector, patch-proposer 等が COBOL 起源コードを読む際に参照する。
---

# COBOL→Java 変換コード読解ガイド

COBOL から Java へ機械変換 or 手動移植されたコードには、idiomatic Java とは異なる特徴的パターンが残ります。これらを理解した上で読み、**勝手にリファクタしない** ことが重要です。

---

## 1. 数値型: COMP-3 → BigDecimal

COBOL の COMP-3（packed decimal）は Java では多くの場合 `BigDecimal` で表現されます。

```java
// 典型例
private BigDecimal amount;  // PIC S9(7)V99 COMP-3 由来

// 計算は scale を意識
BigDecimal result = a.add(b).setScale(2, RoundingMode.HALF_UP);
```

**注意点**:
- `double` / `float` への変換は禁忌（精度落ち）
- `equals` ではなく `compareTo` で等値比較
- scale 不整合のエラーが出やすい

---

## 2. Copybook → DTO クラス

COBOL の copybook（共通データ定義）は Java では DTO / Bean / record として表現されます。多くは `*Copybook.java` `*Message.java` 等の命名。

```java
public class OrderCopybook {
    private String customerCd;     // PIC X(10) 固定長 10 桁
    private BigDecimal totalAmount; // PIC S9(7)V99 COMP-3
    private String reserved1;       // PIC X(20) 予約 (filler)
    // getter/setter
}
```

**注意点**:
- フィールド長は固定。可変長と勘違いしない
- `reserved` `filler` は将来拡張用、勝手に削除しない
- offset / length が電文 layout と一致

---

## 3. 固定長文字列の扱い

COBOL は固定長文字列が基本。Java 側でも以下のパターンが残る:

```java
// 9桁未満は半角スペースで右パディング
String customerCd = String.format("%-10s", input).substring(0, 10);

// trim せずに比較
if ("12345     ".equals(customerCd)) { ... }
```

**注意点**:
- `trim()` を勝手に追加すると COBOL 側との互換性が壊れる
- 半角スペース埋め / 全角スペース埋めの違いに注意
- `equals` で空白付き文字列と空白なしを比較すると false

---

## 4. レベル番号の名残

COBOL の階層構造（01, 05, 10）が Java のネストクラスや getter チェーンになっている場合:

```java
order.getCustomer().getAddress().getZipCode()  // 01-05-10 階層由来
```

**注意点**:
- null チェックの抜けが起こりやすい
- Optional 化していない COBOL 起源コードが多い

---

## 5. PERFORM 風フロー

COBOL の `PERFORM` は Java でも巨大な if-else ladder や goto-like なフラグ駆動で残ることがある:

```java
public Result process(Input in) {
    Result r = new Result();
    String stage = "INIT";

    while (true) {
        if ("INIT".equals(stage)) {
            // ... 何らかの処理
            stage = "VALIDATE";
            continue;
        }
        if ("VALIDATE".equals(stage)) {
            if (!isValid(in)) { r.setErrorFlag(true); break; }
            stage = "PROCESS";
            continue;
        }
        if ("PROCESS".equals(stage)) { ... }
        // ...
        if ("END".equals(stage)) break;
    }
    return r;
}
```

**注意点**:
- 「綺麗にすべき」と思っても **リファクタ禁止**（bug_scope_only）
- フラグ名（stage / errorFlag / endFlag）の意味は元 COBOL を踏襲
- 条件分岐の順序を変えると挙動が変わる可能性大

---

## 6. 巨大メソッド

1 メソッド数百〜千行は珍しくない。

**注意点**:
- 分割したくなるが我慢
- 修正時は最小限の差分に留める
- aider edit-block で SEARCH / REPLACE 範囲を絞る

---

## 7. フラグ駆動の例外処理

COBOL では例外という概念が無いため、フラグで伝搬する設計が残る:

```java
public class Result {
    private boolean errorFlag;
    private String errorCd;
    private String errorMsg;
}

// 上位で
Result r = service.process(in);
if (r.isErrorFlag()) {
    // エラーコードに応じて分岐
}
```

**注意点**:
- `throw new Exception()` に置き換えたくなるが既存 caller が全て影響
- リファクタは別タスク、bug fix の範囲では維持

---

## 8. SQL の COBOL 流

```java
// COBOL の OCCURS をループで再現
for (int i = 0; i < count; i++) {
    OrderItem item = dao.findByIndex(orderId, i);  // 1件ずつ取得
}
```

**注意点**:
- 一括 SELECT に書き換えると性能改善するが、COBOL 側の前提（カーソル開閉、ロック粒度）が崩れる可能性
- 性能改善は別 incident として扱う

---

## まとめ: 5 原則

1. **COMP-3 / 固定長 / copybook は変えない**
2. **`trim()` `Optional` 等の idiomatic 追加は避ける**
3. **フラグ駆動・巨大メソッドはそのまま**
4. **修正は bug 直接対応のみ、リファクタ禁止**
5. **元 COBOL の意図を尊重**

これらは「悪いコード」ではなく「**COBOL 仕様遵守の結果**」です。
