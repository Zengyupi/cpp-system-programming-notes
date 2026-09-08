# XML 数据格式与解析

> 本节目标：系统讲解 XML（eXtensible Markup Language）的语法规范、文档结构、命名空间、DTD/XML Schema 校验、DOM/SAX/StAX 三种解析模型、C++ 主流 XML 解析库的选型与用法、XPath 查询、XSLT 转换、以及 XML 与 JSON 的选型对比和常见坑。学完后能够根据文档大小和访问模式选择合适的解析方式，写出健壮的 XML 处理代码，并理解 XML 在企业系统、配置文件和文档处理中的定位。与《04-JSON数据格式与解析.md》《03-Protobuf序列化协议.md》构成序列化三剑客。

## 本章速览

- [1. XML 概述与设计哲学](#1-xml-概述与设计哲学)
  - [1.1 什么是 XML](#11-什么是-xml)
  - [1.2 XML 的典型应用场景](#12-xml-的典型应用场景)
- [2. XML 语法规范](#2-xml-语法规范)
  - [2.1 完整示例](#21-完整示例)
  - [2.2 语法规则速查](#22-语法规则速查)
  - [2.3 字符转义与 CDATA](#23-字符转义与-cdata)
  - [2.4 格式良好（Well-Formed）vs 有效（Valid）](#24-格式良好well-formedvs-有效valid)
- [3. XML 文档结构](#3-xml-文档结构)
  - [3.1 组成部分详解](#31-组成部分详解)
  - [3.2 元素 vs 属性：设计决策](#32-元素-vs-属性设计决策)
- [4. 命名空间（Namespace）](#4-命名空间namespace)
  - [4.1 为什么需要命名空间](#41-为什么需要命名空间)
  - [4.2 命名空间声明方式](#42-命名空间声明方式)
  - [4.3 命名空间的常见坑](#43-命名空间的常见坑)
- [5. DTD 与 XML Schema](#5-dtd-与-xml-schema)
  - [5.1 DTD（Document Type Definition）](#51-dtddocument-type-definition)
  - [5.2 XML Schema（XSD）](#52-xml-schemaxsd)
  - [5.3 DTD vs XML Schema 对比](#53-dtd-vs-xml-schema-对比)
- [6. XML 解析模型](#6-xml-解析模型)
  - [6.1 DOM vs SAX vs StAX 全面对比](#61-dom-vs-sax-vs-stax-全面对比)
  - [6.2 如何选择解析模型](#62-如何选择解析模型)
- [7. C++ XML 解析库详解](#7-c-xml-解析库详解)
  - [7.1 pugixml（推荐首选，轻量快速）](#71-pugixml推荐首选轻量快速)
  - [7.2 tinyxml2（简单易用）](#72-tinyxml2简单易用)
  - [7.3 libxml2（功能最全，C 库）](#73-libxml2功能最全c-库)
  - [7.4 库选型决策](#74-库选型决策)
- [8. XPath 查询语言](#8-xpath-查询语言)
  - [8.1 常用 XPath 表达式](#81-常用-xpath-表达式)
  - [8.2 XPath 轴（Axis）](#82-xpath-轴axis)
- [9. XSLT 转换](#9-xslt-转换)
- [10. XML vs JSON 选型对比](#10-xml-vs-json-选型对比)
- [11. 常见坑与最佳实践](#11-常见坑与最佳实践)
  - [11.1 常见坑汇总](#111-常见坑汇总)
  - [11.2 最佳实践](#112-最佳实践)
- [12. 快速参考卡片](#12-快速参考卡片)

---

## 1. XML 概述与设计哲学

### 1.1 什么是 XML

XML（eXtensible Markup Language，可扩展标记语言）是一种**元标记语言**——它不预定义标签，而是让使用者自行定义标签和文档结构。XML 由 W3C 于 1998 年发布（XML 1.0），最新版本为 XML 1.1（2004 年，使用较少，XML 1.0 仍是主流）。

XML 的核心设计哲学：
- **可扩展**：标签名、属性名、文档结构完全由使用者定义
- **自描述**：标签名自带语义，人和机器都能理解数据含义
- **结构化**：严格的嵌套层级，天然表示树状数据
- **可验证**：通过 DTD 或 XML Schema 强制约束文档结构
- **文本化**：纯文本格式，跨平台、可阅读、可版本控制

### 1.2 XML 的典型应用场景

| 场景 | 说明 | 代表 |
|---|---|---|
| 配置文件 | 许多框架和工具用 XML 做配置 | Spring、Maven、pom.xml、web.xml、.NET config |
| Web Service | SOAP 协议基于 XML | 企业级系统集成、WSDL 描述 |
| 文档格式 | 办公文档本质是 XML 压缩包 | Office Open XML（.docx/.xlsx）、ODF |
| 数据交换 | 企业间 B2B 数据交换 | 电子发票、海关报文、金融报文 |
| 新闻出版 | 新闻行业的标准交换格式 | NewsML、NITF、RSS/Atom |
| 图形/矢量 | 矢量图形格式 | SVG、MathML |
| 构建工具 | 构建描述文件 | Ant、Maven、NuGet |
| 工业/电力 | 工业设备配置和数据描述 | IEC 61850 SCL（变电站配置描述语言） |

---

## 2. XML 语法规范

### 2.1 完整示例

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- 书店库存文档 -->
<bookstore xmlns:bk="http://example.com/book">
    <book id="1" category="编程">
        <title lang="zh-CN">C++ Primer</title>
        <author>Stanley B. Lippman</author>
        <price currency="CNY">128.00</price>
        <bk:edition>5th</bk:edition>
    </book>
    <book id="2" category="编程">
        <title lang="en">Effective C++</title>
        <author>Scott Meyers</author>
        <price currency="CNY">79.00</price>
        <bk:edition>3rd</bk:edition>
    </book>
</bookstore>
```

### 2.2 语法规则速查

| 规则 | 说明 | 反例 |
|---|---|---|
| 必须有 XML 声明（推荐） | `<?xml version="1.0" encoding="UTF-8"?>` | 省略声明可能导致编码识别错误 |
| 必须有且仅有一个根元素 | 所有内容包裹在唯一根标签内 | 两个并列根元素非法 |
| 标签必须闭合 | `<tag></tag>` 或自闭合 `<tag/>` | `<tag>` 不闭合非法 |
| 标签必须正确嵌套 | `<a><b></b></a>` | `<a><b></a></b>` 交叉嵌套非法 |
| 大小写敏感 | `<Book>` ≠ `<book>` | 开始和结束标签大小写必须一致 |
| 属性值必须加引号 | `id="1"` 或 `id='1'` | `id=1` 无引号非法 |
| 特殊字符必须转义 | `<` → `&lt;`，`&` → `&amp;` | 文本中直接写 `<` 或 `&` 非法 |
| 注释不能含 `--` | `<!-- comment -->` | `<!-- invalid -- comment -->` 非法 |
| 保留的实体引用 | `&lt;` `&gt;` `&amp;` `&quot;` `&apos;` | 其他实体需在 DTD 中定义 |

### 2.3 字符转义与 CDATA

XML 中有 5 个预定义实体引用：

| 实体引用 | 对应字符 | 说明 |
|---|---|---|
| `&lt;` | `<` | 小于号 |
| `&gt;` | `>` | 大于号（严格说不必转义，但建议转义） |
| `&amp;` | `&` | 和号（必须转义，否则会被解析为实体引用开始） |
| `&quot;` | `"` | 双引号（属性值中用双引号包裹时需转义） |
| `&apos;` | `'` | 单引号（属性值中用单引号包裹时需转义） |

当文本中包含大量特殊字符（如代码片段）时，用 **CDATA 段**避免逐个转义：

```xml
<code>
<![CDATA[
    if (a < b && c > d) {
        printf("hello\n");
    }
]]>
</code>
```

CDATA 段内的内容**不做任何解析**，原样保留。注意：CDATA 段不能嵌套，且不能包含字符串 `]]>`。

### 2.4 格式良好（Well-Formed）vs 有效（Valid）

| 概念 | 含义 | 检查内容 |
|---|---|---|
| Well-Formed（格式良好） | 符合 XML 语法规则 | 标签闭合、正确嵌套、属性加引号、特殊字符转义 |
| Valid（有效） | 格式良好 + 符合 DTD/Schema 约束 | 元素结构、属性类型、数据类型、枚举值、出现次数 |

所有 XML 解析器都要求文档格式良好；有效性校验是可选的，需要加载 DTD 或 XML Schema。

---

## 3. XML 文档结构

### 3.1 组成部分详解

| 组件 | 说明 | 示例 |
|---|---|---|
| XML 声明 | 文档开头的处理指令，指定版本和编码 | `<?xml version="1.0" encoding="UTF-8"?>` |
| 处理指令 PI | 给应用程序的指令，以 `<?` 开头 `?>` 结尾 | `<?xml-stylesheet type="text/xsl" href="style.xsl"?>` |
| 注释 | 文档注释，`<!-- -->` | `<!-- 这是注释 -->` |
| 元素 Element | 标签 + 内容，是 XML 的基本构建块 | `<title>C++ Primer</title>` |
| 属性 Attribute | 元素的附加元数据，写在开始标签中 | `<book id="1" category="编程">` |
| 文本 Text | 元素的字符内容 | `C++ Primer` |
| CDATA 段 | 不解析的字符数据 | `<![CDATA[...]]>` |
| 命名空间 | 避免标签名冲突的机制 | `xmlns:bk="http://example.com/book"` |
| DTD/Schema | 文档结构定义和校验规则 | `<!DOCTYPE ...>` 或 `<xs:schema>` |

### 3.2 元素 vs 属性：设计决策

XML 中数据可以放在元素内容中，也可以放在属性中。如何选择？

| 维度 | 元素（Element） | 属性（Attribute） |
|---|---|---|
| 可包含子结构 | 是（可嵌套子元素） | 否（只能是简单文本） |
| 可包含多值 | 是（多个子元素） | 否（单个值，需自己分隔） |
| 可包含特殊字符 | 是（用 CDATA 或转义） | 是（需转义，不能用 CDATA） |
| 可读性 | 好（标签名清晰） | 紧凑但长属性值难读 |
| 可扩展性 | 好（随时加子元素） | 差（改属性可能影响解析） |
| 元数据语义 | 适合数据本身 | 适合关于数据的描述（ID、类型、状态） |

**经验法则**：
- **数据本身用元素**，**关于数据的元数据用属性**
- 如果值可能需要扩展为结构化数据，用元素
- ID、类型、状态、语言等标识性信息用属性
- 不要把多个值塞在一个属性里用分隔符（如 `tags="C++,Linux,Java"`），应该用多个子元素

```xml
<!-- 推荐：数据用元素，元数据用属性 -->
<book id="1" category="编程" status="in-stock">
    <title>C++ Primer</title>
    <author>Stanley B. Lippman</author>
    <price currency="CNY">128.00</price>
    <tags>
        <tag>C++</tag>
        <tag>programming</tag>
    </tags>
</book>
```

---

## 4. 命名空间（Namespace）

### 4.1 为什么需要命名空间

XML 允许自定义标签名，当文档中混合来自不同词汇表的元素时，标签名可能冲突：

```xml
<!-- 冲突：两个 table 含义不同 -->
<root>
    <table>            <!-- HTML 的表格 -->
        <tr><td>数据</td></tr>
    </table>
    <table>            <!-- 家具的桌子 -->
        <width>120</width>
        <height>75</height>
    </table>
</root>
```

命名空间通过 **URI + 前缀** 区分不同词汇表：

```xml
<root xmlns:h="http://www.w3.org/1999/xhtml"
      xmlns:f="http://example.com/furniture">
    <h:table>
        <h:tr><h:td>数据</h:td></h:tr>
    </h:table>
    <f:table>
        <f:width>120</f:width>
        <f:height>75</f:height>
    </f:table>
</root>
```

### 4.2 命名空间声明方式

| 方式 | 语法 | 说明 |
|---|---|---|
| 带前缀 | `xmlns:prefix="URI"` | 该前缀下的元素属于此命名空间 |
| 默认命名空间 | `xmlns="URI"` | 无前缀的元素默认属于此命名空间 |
| 作用域 | 声明在哪个元素上，就作用于该元素及其所有后代 | 子元素可以覆盖父元素的命名空间声明 |

> **注意**：命名空间 URI 只是一个**唯一标识符**，不要求是可访问的网址。它的作用是提供全局唯一性，解析器不会去访问这个 URI。

### 4.3 命名空间的常见坑

| 坑 | 说明 |
|---|---|
| XPath 查询忘记加命名空间 | 文档有默认命名空间时，XPath `//book` 查不到，必须用 `//*[local-name()='book']` 或注册命名空间前缀 |
| 命名空间前缀变化导致代码失效 | 前缀只是别名，URI 才是身份。代码应基于 URI 判断，不要硬编码前缀 |
| 属性的命名空间 | 不带前缀的属性**不属于**任何命名空间（即使元素有默认命名空间）。带前缀的属性才属于对应命名空间 |
| 默认命名空间不作用于属性 | `xmlns="uri"` 只影响元素名，不影响无前缀的属性名 |

---

## 5. DTD 与 XML Schema

### 5.1 DTD（Document Type Definition）

DTD 是 XML 1.0 自带的文档结构定义语言，语法简洁但功能有限。

```xml
<!DOCTYPE bookstore [
    <!ELEMENT bookstore (book+)>
    <!ELEMENT book (title, author, price)>
    <!ATTLIST book id ID #REQUIRED category CDATA #IMPLIED>
    <!ELEMENT title (#PCDATA)>
    <!ATTLIST title lang CDATA "zh-CN">
    <!ELEMENT author (#PCDATA)>
    <!ELEMENT price (#PCDATA)>
    <!ATTLIST price currency (CNY|USD|EUR) "CNY">
]>
```

| DTD 语法 | 含义 |
|---|---|
| `<!ELEMENT name (content)>` | 定义元素及其内容模型 |
| `<!ATTLIST element attr type default>` | 定义元素的属性 |
| `(#PCDATA)` | 纯文本内容 |
| `(child1, child2)` | 顺序出现子元素 |
| `(choice1\|choice2)` | 选择其一 |
| `+` | 出现一次或多次 |
| `*` | 出现零次或多次 |
| `?` | 出现零次或一次 |
| `#REQUIRED` | 属性必需 |
| `#IMPLIED` | 属性可选 |
| `#FIXED "value"` | 属性固定值 |

### 5.2 XML Schema（XSD）

XML Schema Definition（XSD）是 W3C 推荐的替代 DTD 的 schema 语言，功能强大，支持数据类型、命名空间、复杂约束。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:element name="bookstore">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="book" maxOccurs="unbounded">
                    <xs:complexType>
                        <xs:sequence>
                            <xs:element name="title" type="xs:string"/>
                            <xs:element name="author" type="xs:string"/>
                            <xs:element name="price">
                                <xs:complexType>
                                    <xs:simpleContent>
                                        <xs:extension base="xs:decimal">
                                            <xs:attribute name="currency" default="CNY">
                                                <xs:simpleType>
                                                    <xs:restriction base="xs:string">
                                                        <xs:enumeration value="CNY"/>
                                                        <xs:enumeration value="USD"/>
                                                        <xs:enumeration value="EUR"/>
                                                    </xs:restriction>
                                                </xs:simpleType>
                                            </xs:attribute>
                                        </xs:extension>
                                    </xs:simpleContent>
                                </xs:complexType>
                            </xs:element>
                        </xs:sequence>
                        <xs:attribute name="id" type="xs:integer" use="required"/>
                        <xs:attribute name="category" type="xs:string"/>
                    </xs:complexType>
                </xs:element>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
```

### 5.3 DTD vs XML Schema 对比

| 维度 | DTD | XML Schema（XSD） |
|---|---|---|
| 语法 | 非 XML 语法（自己的语法） | XML 语法（本身就是 XML 文档） |
| 数据类型 | 有限（CDATA、ID、IDREF、枚举） | 丰富（string、integer、decimal、date、boolean 等 44 种内置类型） |
| 命名空间支持 | 不支持 | 原生支持 |
| 复杂约束 | 弱（只能定义元素顺序和出现次数） | 强（支持 key/keyref、unique、类型继承、正则约束） |
| 可扩展性 | 差 | 好（可自定义简单类型和复杂类型） |
| 学习曲线 | 简单 | 较陡 |
| 适用场景 | 简单文档、遗留系统 | 企业级系统、强数据校验、Web Service |

---

## 6. XML 解析模型

### 6.1 DOM vs SAX vs StAX 全面对比

| 维度 | DOM（Document Object Model） | SAX（Simple API for XML） | StAX（Streaming API for XML） |
|---|---|---|---|
| 工作方式 | 一次性加载整个文档，构建内存树 | 流式读取，事件回调（推模式） | 流式读取，应用主动拉取（拉模式） |
| 内存占用 | 高（文档的 5-10 倍） | 低（恒定，只保留当前状态） | 低（恒定） |
| 访问方式 | 随机访问任意节点 | 只能顺序，无法回溯 | 顺序，但可主动控制读取节奏 |
| 易用性 | 高（直接操作树） | 低（需写状态机/回调） | 中（迭代器风格，比 SAX 直观） |
| 修改文档 | 支持（可修改树再序列化） | 不支持（只读） | 不支持（只读） |
| XPath 查询 | 支持 | 不支持 | 不支持 |
| 适用场景 | 中小文档、需要随机访问/修改 | 超大文档、只提取部分字段、流式管道 | 超大文档、需要精细控制读取流程 |
| C++ 代表库 | pugixml、tinyxml2、libxml2 DOM、Xerces DOM | libxml2 SAX、Xerces SAX | libxml2 XmlReader、Xerces StAX |

### 6.2 如何选择解析模型

```text
需要解析 XML 文档？
    │
    ├─ 文档 < 10MB，需要随机访问或修改？
    │   └─ DOM（pugixml / tinyxml2）
    │
    ├─ 文档 > 10MB，只需要提取部分数据？
    │   └─ SAX 或 StAX（libxml2）
    │
    ├─ 需要 XPath 查询？
    │   └─ DOM + XPath（pugixml 支持 XPath 1.0）
    │
    └─ 需要修改并重新输出？
        └─ DOM（可修改树节点后 dump 为 XML）
```

---

## 7. C++ XML 解析库详解

### 7.1 pugixml（推荐首选，轻量快速）

**特点**：轻量级（单头文件+单源文件，约 400KB）、快速、DOM 模型、支持 XPath 1.0、支持 UTF-8/UTF-16/UTF-32。

```cpp
#include "pugixml.hpp"
#include <iostream>

// ===== 加载文档 =====
pugi::xml_document doc;
pugi::xml_parse_result result = doc.load_file("books.xml");

if (!result) {
    std::cerr << "XML 解析失败: " << result.description()
              << " at offset " << result.offset << '\n';
    return 1;
}

// ===== 遍历节点 =====
pugi::xml_node root = doc.child("bookstore");
for (pugi::xml_node book : root.children("book")) {
    // 读取属性
    const char* id = book.attribute("id").value();
    const char* category = book.attribute("category").value();

    // 读取子元素文本
    const char* title = book.child_value("title");
    const char* author = book.child_value("author");

    // 读取带属性的子元素
    pugi::xml_node price_node = book.child("price");
    double price = price_node.text().as_double();
    const char* currency = price_node.attribute("currency").value();

    std::cout << id << ": " << title << " by " << author
              << " (" << price << " " << currency << ")\n";
}

// ===== XPath 查询 =====
// 查找所有价格 > 100 的书
pugi::xpath_node_set expensive_books =
    root.select_nodes("//book[price > 100]");
for (pugi::xpath_node node : expensive_books) {
    std::cout << "贵的书: " << node.node().child_value("title") << '\n';
}

// 查找第一本编程类书的标题
pugi::xpath_node first_prog =
    root.select_node("//book[@category='编程']/title");
if (first_prog) {
    std::cout << "第一本编程书: " << first_prog.node().text().get() << '\n';
}

// ===== 修改文档 =====
pugi::xml_node new_book = root.append_child("book");
new_book.append_attribute("id") = "3";
new_book.append_attribute("category") = "编程";
new_book.append_child("title").text() = "Modern C++";
new_book.append_child("author").text() = "Someone";
pugi::xml_node new_price = new_book.append_child("price");
new_price.text() = 99.0;
new_price.append_attribute("currency") = "CNY";

// 保存到文件
doc.save_file("books_updated.xml", "  ");  // 第二个参数是缩进
```

**pugixml 的解析选项**：

| 选项 | 说明 |
|---|---|
| `pugi::parse_default` | 默认：解析 CDATA、注释、PI，声明 |
| `pugi::parse_minimal` | 最小：只解析元素和文本 |
| `pugi::parse_full` | 完整：解析所有内容包括 DOCTYPE |
| `pugi::parse_trim_pcdata` | 去除文本前后空白 |
| `pugi::parse_escapes` | 转换 `\n` 等转义（默认已开） |
| `pugi::encoding_utf8` | UTF-8 编码（默认） |
| `pugi::encoding_utf16` | UTF-16 编码 |

### 7.2 tinyxml2（简单易用）

**特点**：极简 API、DOM 模型、单头文件+单源文件、C++11 即可用。不支持 XPath。

```cpp
#include "tinyxml2.h"
using namespace tinyxml2;

XMLDocument doc;
if (doc.LoadFile("books.xml") != XML_SUCCESS) {
    std::cerr << "加载失败\n";
    return 1;
}

XMLElement* root = doc.FirstChildElement("bookstore");
for (XMLElement* book = root->FirstChildElement("book");
     book != nullptr;
     book = book->NextSiblingElement("book")) {

    const char* id = book->Attribute("id");
    const char* title = book->FirstChildElement("title")->GetText();
    const char* author = book->FirstChildElement("author")->GetText();

    XMLElement* price_elem = book->FirstChildElement("price");
    double price = price_elem->DoubleText();
    const char* currency = price_elem->Attribute("currency");
}

// 保存
doc.SaveFile("output.xml");
```

### 7.3 libxml2（功能最全，C 库）

**特点**：Gnome 项目的 C 语言 XML 库，功能最全（DOM/SAX/StAX/XPath/XSLT/Schema 校验），但 API 是 C 风格，需要手动管理内存。

```cpp
#include <libxml/parser.h>
#include <libxml/xpath.h>

// 初始化
xmlInitParser();

// 解析文档
xmlDocPtr doc = xmlReadFile("books.xml", NULL, 0);
if (!doc) { /* 错误处理 */ }

// XPath 查询
xmlXPathContextPtr ctx = xmlXPathNewContext(doc);
xmlXPathObjectPtr result = xmlXPathEvalExpression(
    BAD_CAST "//book[price > 100]/title", ctx);

if (result && result->nodesetval) {
    for (int i = 0; i < result->nodesetval->nodeNr; i++) {
        xmlNodePtr node = result->nodesetval->nodeTab[i];
        xmlChar* content = xmlNodeGetContent(node);
        printf("%s\n", content);
        xmlFree(content);
    }
}

// 释放（libxml2 必须手动释放！）
xmlXPathFreeObject(result);
xmlXPathFreeContext(ctx);
xmlFreeDoc(doc);
xmlCleanupParser();
```

### 7.4 库选型决策

| 库 | 大小 | 解析模型 | XPath | Schema 校验 | XSLT | 易用性 | 适用场景 |
|---|---|---|---|---|---|---|---|
| pugixml | ~400KB | DOM | 1.0 | 否 | 否 | 高 | 通用首选，中小文档 |
| tinyxml2 | ~50KB | DOM | 否 | 否 | 否 | 高 | 极简需求，嵌入式 |
| libxml2 | ~1MB+ | DOM/SAX/StAX | 1.0/2.0 | 是 | 是 | 中（C API） | 功能最全，企业级 |
| Xerces-C++ | ~3MB+ | DOM/SAX/StAX | 1.0 | 是 | 否 | 中 | Apache 项目，Java 生态兼容 |
| RapidXML | ~40KB | DOM（in-place） | 否 | 否 | 否 | 中 | 极致性能，零拷贝 |

> **推荐**：大多数 C++ 项目用 **pugixml** 即可——轻量、快速、支持 XPath、API 友好。只有需要 SAX/StAX 流式解析或 Schema 校验时才考虑 libxml2。

---

## 8. XPath 查询语言

XPath 是在 XML 文档中查找信息的语言，是 XSLT、XQuery 和许多 XML API 的基础。

### 8.1 常用 XPath 表达式

| 表达式 | 含义 | 示例结果 |
|---|---|---|
| `bookstore` | 选择 bookstore 的所有子元素 | 根下的 bookstore |
| `//book` | 选择文档中所有 book 元素（任意位置） | 所有 book |
| `//book/title` | 选择所有 book 的 title 子元素 | 所有书名 |
| `//book[@id='1']` | 选择 id 属性为 1 的 book | 第一本书 |
| `//book[@category='编程']` | 选择 category 为编程的书 | 编程类书籍 |
| `//book[price > 100]` | 选择 price > 100 的书 | 贵的书 |
| `//book[1]` | 选择第一本 book | 第一本书 |
| `//book[last()]` | 选择最后一本 book | 最后一本书 |
| `//book/title/text()` | 选择 title 的文本内容 | 书名字符串 |
| `//book/@id` | 选择所有 book 的 id 属性 | id 值列表 |
| `//*[local-name()='book']` | 忽略命名空间选择 book | 有默认命名空间时用这个 |

### 8.2 XPath 轴（Axis）

| 轴 | 含义 |
|---|---|
| `child::` | 子节点（默认轴） |
| `descendant::` | 所有后代节点 |
| `parent::` | 父节点 |
| `ancestor::` | 所有祖先节点 |
| `following-sibling::` | 后续兄弟节点 |
| `preceding-sibling::` | 前序兄弟节点 |
| `attribute::` | 属性节点（简写 `@`） |

---

## 9. XSLT 转换

XSLT（eXtensible Stylesheet Language Transformations）是将 XML 文档转换为其他格式（HTML、文本、另一种 XML）的语言。

```xml
<!-- books.xsl：将书店 XML 转换为 HTML 表格 -->
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
    <xsl:template match="/">
        <html>
        <body>
            <h2>书店库存</h2>
            <table border="1">
                <tr>
                    <th>ID</th><th>书名</th><th>作者</th><th>价格</th>
                </tr>
                <xsl:for-each select="bookstore/book">
                    <tr>
                        <td><xsl:value-of select="@id"/></td>
                        <td><xsl:value-of select="title"/></td>
                        <td><xsl:value-of select="author"/></td>
                        <td><xsl:value-of select="price"/></td>
                    </tr>
                </xsl:for-each>
            </table>
        </body>
        </html>
    </xsl:template>
</xsl:stylesheet>
```

C++ 中可用 libxml2 + libxslt 执行 XSLT 转换。

---

## 10. XML vs JSON 选型对比

| 维度 | XML | JSON |
|---|---|---|
| 格式 | 文本（标签式） | 文本（键值对式） |
| 可读性 | 好（但标签冗长） | 好（简洁） |
| 体积 | 大（开闭标签重复） | 小（键名重复但比标签短） |
| 解析速度 | 慢（标签解析、命名空间处理） | 快（语法简单） |
| Schema | DTD/XSD（强约束，成熟） | JSON Schema（较新，功能弱于 XSD） |
| 命名空间 | 原生支持 | 不支持（靠键名前缀约定） |
| 属性 | 支持（元素 vs 属性的设计选择） | 不支持（一切都是键值对） |
| 注释 | 支持 | 不支持（标准 JSON） |
| 二进制 | 需 Base64/CDATA | 需 Base64 |
| 数据类型 | 文本为主（Schema 可约束类型） | 6 种原生类型（string/number/boolean/null/object/array） |
| 混合内容 | 支持（文本+子元素混合，适合文档） | 不支持 |
| 工具生态 | 成熟（XPath/XSLT/XQuery/Schema 全套） | 丰富（但工具链不如 XML 完整） |
| 适用场景 | 配置文件、文档、企业集成、Web Service、需要强 schema | Web API、前后端通信、轻量配置、日志 |

**选型决策**：

```text
选择数据交换格式？
    │
    ├─ 面向 Web API / 前后端通信？
    │   └─ JSON（简洁、解析快、JavaScript 原生支持）
    │
    ├─ 面向企业系统集成 / B2B / 强 schema 校验？
    │   └─ XML（XSD 强约束、命名空间、成熟的企业工具链）
    │
    ├─ 面向文档处理 / 混合内容 / 出版？
    │   └─ XML（支持混合内容、XSLT 转换、DocBook/DITA 等）
    │
    ├─ 面向配置文件？
    │   ├─ 需要注释和强 schema → XML
    │   └─ 简洁易用 → JSON（或 YAML/TOML）
    │
    └─ 面向高性能内部 RPC？
        └─ Protobuf（二进制、极致性能、强 schema）
```

---

## 11. 常见坑与最佳实践

### 11.1 常见坑汇总

| 坑 | 现象 | 解决方案 |
|---|---|---|
| 标签未闭合或交叉嵌套 | 解析报错 | 用 XML 编辑器/插件自动校验，开启格式良好检查 |
| 特殊字符未转义 | `<` `&` 直接出现在文本中导致解析失败 | 用 `&lt;` `&amp;` 转义，或用 CDATA 段 |
| 属性值未加引号 | `id=1` 解析失败 | 属性值一律加引号（双引号或单引号） |
| 大小写不匹配 | `<Book>` 开始 `</book>` 结束解析失败 | XML 大小写敏感，开始和结束标签必须完全一致 |
| 命名空间导致 XPath 查不到 | 文档有默认命名空间时 `//book` 返回空 | 用 `//*[local-name()='book']` 或注册命名空间前缀 |
| 大文件用 DOM 加载 | 内存暴涨甚至 OOM | 大文件用 SAX/StAX 流式解析 |
| libxml2 内存泄漏 | 忘记 xmlFreeDoc / xmlFree | 用 RAII 包装 libxml2 对象，或用 pugixml 等 C++ 原生库 |
| 编码不统一 | 中文乱码 | XML 声明指定 encoding，文件实际编码与声明一致，统一 UTF-8 |
| BOM 头问题 | UTF-8 BOM 导致某些解析器报错 | 用无 BOM 的 UTF-8，或确保解析器处理 BOM |
| 空元素自闭合 vs 开闭标签 | `<book/>` 和 `<book></book>` 语义相同但文本处理可能不同 | 解析后统一处理，不要依赖原始文本格式 |
| DTD 实体注入攻击 | 恶意外部实体引用（XXE）导致文件读取/SSRF | 禁用外部实体解析，libxml2 用 `XML_PARSE_NOENT` 需谨慎 |
| 多个根元素 | 文档有两个并列根元素解析失败 | 确保只有一个根元素，或用 XML 片段（多个文档） |

### 11.2 最佳实践

1. **统一 UTF-8 编码**：XML 声明写 `encoding="UTF-8"`，文件实际保存为 UTF-8（无 BOM）。
2. **中小文档用 pugixml**：轻量、快速、支持 XPath，C++ API 友好。
3. **大文档用流式解析**：超过 10MB 的文档用 SAX/StAX，不要用 DOM。
4. **需要查询用 XPath**：不要手写递归遍历，XPath 表达式更简洁可靠。
5. **数据用元素，元数据用属性**：遵循元素 vs 属性的设计原则。
6. **用命名空间避免冲突**：混合多个词汇表时一定要用命名空间。
7. **XXE 防护**：解析不可信 XML 时禁用外部实体，防止 XXE 攻击。
8. **RAII 管理解析器资源**：libxml2 等 C 库的对象用智能指针或自定义 RAII 类管理。
9. **校验文档有效性**：关键业务数据用 XSD 校验，提前发现结构错误。
10. **不要用 XML 做高性能序列化**：XML 解析慢、体积大，高性能场景用 Protobuf 或 MessagePack。

---

## 12. 快速参考卡片

```text
语法：XML声明 + 单一根元素 + 标签闭合 + 正确嵌套 + 属性加引号 + 特殊字符转义
转义：&lt; &gt; &amp; &quot; &apos;；大量特殊字符用 <![CDATA[...]]>
命名空间：xmlns:prefix="URI" 或 xmlns="URI"(默认)；URI只是标识符不访问
校验：DTD(简单) 或 XML Schema/XSD(强类型+命名空间)
解析模型：DOM(整树随机访问) / SAX(流式事件回调) / StAX(流式拉取)
C++库：pugixml(轻量+XPath首选) / tinyxml2(极简) / libxml2(功能最全C库)
XPath：//book[@id='1'] 按属性查；//book[price>100] 按值查；text()取文本
XSLT：模板匹配 + for-each + value-of，XML转HTML/文本/XML
对比：XML(强schema+命名空间+混合内容，冗长) vs JSON(简洁通用，无schema)
坑：标签未闭合/特殊字符未转义/命名空间XPath查不到/大文件DOM内存爆/XXE攻击/编码不统一
```

---

**延伸阅读**：《04-JSON数据格式与解析.md》讲解另一种主流数据交换格式，《03-Protobuf序列化协议.md》讲解二进制高性能序列化方案。三者的选型对比见本篇第 10 节。

---

上一篇：《04-JSON数据格式与解析.md》
下一篇：《06-Redis深入：协议存储与集群.md》
