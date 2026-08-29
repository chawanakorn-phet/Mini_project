const pptxgen = require("pptxgenjs");

const NAVY = "21295C";
const DEEP_BLUE = "065A82";
const TEAL = "1C7293";
const WHITE = "FFFFFF";
const INK = "1B1F2A";
const MUTED = "5B6472";
const CARD_BG = "F4F7F9";

function newDeck() {
  const p = new pptxgen();
  p.layout = "LAYOUT_WIDE"; // 13.3 x 7.5 in
  return p;
}

function titleSlide(p) {
  const s = p.addSlide();
  s.background = { color: NAVY };
  s.addText("Data Warehouse & Dimensional Model Design", {
    x: 0.8, y: 2.1, w: 11.7, h: 1.3, isTextBox: true, margin: 0,
    fontFace: "Cambria", fontSize: 40, bold: true, color: WHITE, align: "left",
  });
  s.addText("Olist Brazilian E-Commerce Public Dataset", {
    x: 0.8, y: 3.35, w: 11.7, h: 0.6, isTextBox: true, margin: 0,
    fontFace: "Calibri", fontSize: 22, color: "CADCFC", align: "left",
  });
  s.addShape(p.ShapeType.rect, { x: 0.8, y: 4.15, w: 1.4, h: 0.06, fill: { color: TEAL } });
  s.addText("Mini Project: การออกแบบคลังข้อมูลและโมเดลข้อมูลเพื่อตอบสำหรับการวิเคราะห์ธุรกิจ", {
    x: 0.8, y: 4.4, w: 11.7, h: 0.5, isTextBox: true, margin: 0,
    fontFace: "Calibri", fontSize: 16, color: "CADCFC", align: "left",
  });
  s.addText("ชวนากร เพชรเจริญรัตน์  |  GitHub: chawanakorn-phet/Mini_project", {
    x: 0.8, y: 6.7, w: 11.7, h: 0.4, isTextBox: true, margin: 0,
    fontFace: "Calibri", fontSize: 13, color: "8AA0C8", align: "left",
  });
}

function sectionHeader(s, title, sub) {
  s.addText(title, {
    x: 0.7, y: 0.45, w: 11.9, h: 0.7, isTextBox: true, margin: 0,
    fontFace: "Cambria", fontSize: 30, bold: true, color: NAVY,
  });
  if (sub) {
    s.addText(sub, {
      x: 0.7, y: 1.1, w: 11.9, h: 0.4, isTextBox: true, margin: 0,
      fontFace: "Calibri", fontSize: 14, color: MUTED,
    });
  }
}

function operationalDbSlide(p) {
  const s = p.addSlide();
  s.background = { color: WHITE };
  sectionHeader(s, "1. Operational Database: Olist Marketplace", "แพลตฟอร์มมาร์เก็ตเพลสของบราซิล เชื่อมร้านค้ากับลูกค้าทั่วประเทศ (ข้อมูลปี 2016–2018)");

  const facts = [
    ["9", "ตารางต้นทาง (OLTP)"],
    ["~99K", "ออเดอร์"],
    ["~33K", "สินค้าในแคตตาล็อก"],
    ["~3K", "ผู้ขาย (Sellers)"],
  ];
  let fx = 0.7;
  facts.forEach(([num, label]) => {
    s.addShape(p.ShapeType.roundRect, { x: fx, y: 1.75, w: 2.7, h: 1.3, rectRadius: 0.08, fill: { color: CARD_BG }, line: { color: "E1E7EC", width: 1 } });
    s.addText(num, { x: fx, y: 1.85, w: 2.7, h: 0.6, isTextBox: true, margin: 0, align: "center", fontFace: "Cambria", fontSize: 28, bold: true, color: DEEP_BLUE });
    s.addText(label, { x: fx, y: 2.5, w: 2.7, h: 0.45, isTextBox: true, margin: 0, align: "center", fontFace: "Calibri", fontSize: 12, color: MUTED });
    fx += 2.9;
  });

  // simple ER relationship diagram using boxes + connectors
  const boxes = [
    { key: "CUSTOMERS", x: 0.7, y: 3.5 },
    { key: "ORDERS", x: 3.55, y: 3.5 },
    { key: "ORDER_ITEMS", x: 6.4, y: 3.5 },
    { key: "PRODUCTS", x: 9.25, y: 2.7 },
    { key: "SELLERS", x: 9.25, y: 4.3 },
  ];
  const bw = 2.35, bh = 0.75;
  boxes.forEach((b) => {
    s.addShape(p.ShapeType.roundRect, { x: b.x, y: b.y, w: bw, h: bh, rectRadius: 0.06, fill: { color: DEEP_BLUE }, line: { color: DEEP_BLUE, width: 0 } });
    s.addText(b.key, { x: b.x, y: b.y, w: bw, h: bh, isTextBox: true, margin: 0, align: "center", valign: "middle", fontFace: "Calibri", fontSize: 13, bold: true, color: WHITE });
  });
  const mid = (b) => ({ x: b.x + bw / 2, y: b.y + bh / 2 });
  function connector(a, b) {
    s.addShape(p.ShapeType.line, { x: a.x, y: a.y, w: b.x - a.x, h: b.y - a.y, line: { color: "9AA7B5", width: 1.5 } });
  }
  connector({ x: boxes[0].x + bw, y: boxes[0].y + bh / 2 }, { x: boxes[1].x, y: boxes[1].y + bh / 2 });
  connector({ x: boxes[1].x + bw, y: boxes[1].y + bh / 2 }, { x: boxes[2].x, y: boxes[2].y + bh / 2 });
  connector({ x: boxes[2].x + bw, y: boxes[2].y + bh / 2 }, { x: boxes[3].x, y: boxes[3].y + bh / 2 });
  connector({ x: boxes[2].x + bw, y: boxes[2].y + bh / 2 }, { x: boxes[4].x, y: boxes[4].y + bh / 2 });

  s.addText("อีก 4 ตารางสนับสนุน: Order Payments, Order Reviews, Geolocation, Category Translation", {
    x: 0.7, y: 5.35, w: 11.9, h: 0.4, isTextBox: true, margin: 0,
    fontFace: "Calibri", fontSize: 12, italic: true, color: MUTED,
  });
  s.addNotes("ER diagram แบบเต็มอยู่ใน README.md ของ repository (mermaid erDiagram)");
}

function businessQuestionsSlide(p, title, questions, startNum) {
  const s = p.addSlide();
  s.background = { color: WHITE };
  sectionHeader(s, title);
  const col1 = questions.slice(0, 4);
  const col2 = questions.slice(4);
  function renderCol(items, x, offset) {
    let y = 1.55;
    items.forEach((q, i) => {
      s.addShape(p.ShapeType.ellipse, { x, y: y + 0.02, w: 0.36, h: 0.36, fill: { color: TEAL }, line: { width: 0 } });
      s.addText(String(offset + i + 1), { x, y: y + 0.02, w: 0.36, h: 0.36, isTextBox: true, margin: 0, align: "center", valign: "middle", fontFace: "Calibri", fontSize: 13, bold: true, color: WHITE });
      s.addText(q, { x: x + 0.55, y, w: 5.55, h: 1.0, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 13.5, color: INK, valign: "top" });
      y += 1.15;
    });
  }
  renderCol(col1, 0.7, startNum);
  renderCol(col2, 6.65, startNum + 4);
}

function dimensionsSlide(p) {
  const s = p.addSlide();
  s.background = { color: WHITE };
  sectionHeader(s, "3. Multidimensional Data Model — Dimensions", "Fact Constellation (Galaxy Schema): Fact หลายตารางใช้ Dimension ร่วมกัน");

  const dims = [
    ["dim_date", "Day → Month → Quarter → Year", "แจกแจงยอดขายตามเวลาจาก order_purchase_timestamp"],
    ["dim_customers", "Customer → City → State", "grain = 1 แถวต่อ customer_id, เก็บ customer_unique_id สำหรับวิเคราะห์ repeat customer"],
    ["dim_sellers", "Seller → City → State", "grain = 1 แถวต่อ seller_id"],
    ["dim_products", "Product → Category (EN)", "grain = 1 แถวต่อ product_id, แปลชื่อหมวดหมู่เป็นภาษาอังกฤษ"],
  ];
  let x = 0.7;
  dims.forEach(([name, level, desc]) => {
    s.addShape(p.ShapeType.roundRect, { x, y: 1.65, w: 2.85, h: 4.4, rectRadius: 0.08, fill: { color: CARD_BG }, line: { color: "E1E7EC", width: 1 } });
    s.addShape(p.ShapeType.roundRect, { x: x + 0.25, y: 1.95, w: 2.35, h: 0.5, rectRadius: 0.25, fill: { color: DEEP_BLUE }, line: { width: 0 } });
    s.addText(name, { x: x + 0.25, y: 1.95, w: 2.35, h: 0.5, isTextBox: true, margin: 0, align: "center", valign: "middle", fontFace: "Calibri", fontSize: 13, bold: true, color: WHITE });
    s.addText("Level", { x: x + 0.25, y: 2.65, w: 2.35, h: 0.3, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 11, bold: true, color: TEAL });
    s.addText(level, { x: x + 0.25, y: 2.95, w: 2.35, h: 0.9, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 12, color: INK });
    s.addText("รายละเอียด", { x: x + 0.25, y: 3.85, w: 2.35, h: 0.3, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 11, bold: true, color: TEAL });
    s.addText(desc, { x: x + 0.25, y: 4.15, w: 2.35, h: 1.75, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 11, color: MUTED });
    x += 3.0;
  });
}

function factsSlide(p) {
  const s = p.addSlide();
  s.background = { color: WHITE };
  sectionHeader(s, "3. Multidimensional Data Model — Fact Tables", "3 Fact ใช้ Dimension ร่วมกัน (conformed dimensions: dim_date, dim_customers)");

  const facts = [
    ["fact_order_items", "1 แถว / รายการสินค้าในออเดอร์\n(order_id + order_item_id)", "price, freight_value,\ntotal_item_value, delivery_days"],
    ["fact_order_payments", "1 แถว / การชำระเงิน\n(order_id + payment_sequential)", "payment_value,\npayment_installments"],
    ["fact_order_reviews", "1 แถว / รีวิว\n(review_id)", "review_score, has_comment"],
  ];
  let x = 0.9;
  facts.forEach(([name, grain, measures]) => {
    s.addShape(p.ShapeType.roundRect, { x, y: 1.8, w: 3.6, h: 3.9, rectRadius: 0.08, fill: { color: CARD_BG }, line: { color: "E1E7EC", width: 1 } });
    s.addShape(p.ShapeType.rect, { x, y: 1.8, w: 3.6, h: 0.7, fill: { color: NAVY }, line: { width: 0 } });
    s.addText(name, { x, y: 1.8, w: 3.6, h: 0.7, isTextBox: true, margin: 0, align: "center", valign: "middle", fontFace: "Calibri", fontSize: 15, bold: true, color: WHITE });
    s.addText("Grain", { x: x + 0.3, y: 2.75, w: 3.0, h: 0.3, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 12, bold: true, color: TEAL });
    s.addText(grain, { x: x + 0.3, y: 3.05, w: 3.0, h: 1.0, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 12, color: INK });
    s.addText("Measures", { x: x + 0.3, y: 4.1, w: 3.0, h: 0.3, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 12, bold: true, color: TEAL });
    s.addText(measures, { x: x + 0.3, y: 4.4, w: 3.0, h: 1.1, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 12, color: INK });
    x += 3.85;
  });
}

function starSchemaSlide(p) {
  const s = p.addSlide();
  s.background = { color: WHITE };
  sectionHeader(s, "4. Data Model Diagram — Fact Constellation");

  const factBoxes = [
    { key: "fact_order_items", x: 5.0, y: 1.7 },
    { key: "fact_order_payments", x: 5.0, y: 2.75 },
    { key: "fact_order_reviews", x: 5.0, y: 3.8 },
  ];
  const dimBoxes = [
    { key: "dim_date", x: 0.7, y: 1.4 },
    { key: "dim_customers", x: 0.7, y: 4.1 },
    { key: "dim_products", x: 9.8, y: 1.4 },
    { key: "dim_sellers", x: 9.8, y: 4.1 },
  ];
  const fw = 3.3, fh = 0.7, dw = 2.8, dh = 0.7;

  factBoxes.forEach((b) => {
    s.addShape(p.ShapeType.roundRect, { x: b.x, y: b.y, w: fw, h: fh, rectRadius: 0.06, fill: { color: NAVY }, line: { width: 0 } });
    s.addText(b.key, { x: b.x, y: b.y, w: fw, h: fh, isTextBox: true, margin: 0, align: "center", valign: "middle", fontFace: "Calibri", fontSize: 13, bold: true, color: WHITE });
  });
  dimBoxes.forEach((b) => {
    s.addShape(p.ShapeType.roundRect, { x: b.x, y: b.y, w: dw, h: dh, rectRadius: 0.06, fill: { color: TEAL }, line: { width: 0 } });
    s.addText(b.key, { x: b.x, y: b.y, w: dw, h: dh, isTextBox: true, margin: 0, align: "center", valign: "middle", fontFace: "Calibri", fontSize: 13, bold: true, color: WHITE });
  });

  function line(x1, y1, x2, y2) {
    s.addShape(p.ShapeType.line, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1), line: { color: "B9C2CC", width: 1.25 } });
  }
  // date -> all 3 facts ; customers -> all 3 facts
  factBoxes.forEach((f) => {
    line(dimBoxes[0].x + dw, dimBoxes[0].y + dh / 2, f.x, f.y + fh / 2);
    line(dimBoxes[1].x + dw, dimBoxes[1].y + dh / 2, f.x, f.y + fh / 2);
  });
  // products/sellers -> fact_order_items only
  line(dimBoxes[2].x, dimBoxes[2].y + dh / 2, factBoxes[0].x + fw, factBoxes[0].y + fh / 2);
  line(dimBoxes[3].x, dimBoxes[3].y + dh / 2, factBoxes[0].x + fw, factBoxes[0].y + fh / 2);

  s.addText("dim_date และ dim_customers เป็น conformed dimension เชื่อมทั้ง 3 fact ส่วน dim_products/dim_sellers เชื่อมเฉพาะ fact_order_items", {
    x: 0.7, y: 5.3, w: 11.9, h: 0.5, isTextBox: true, margin: 0,
    fontFace: "Calibri", fontSize: 12, italic: true, color: MUTED,
  });
}

function etlSlide(p) {
  const s = p.addSlide();
  s.background = { color: WHITE };
  sectionHeader(s, "5. ETL / ELT Process", "แนวทาง ELT ผ่าน dbt + DuckDB");

  const steps = [
    ["Extract", "CSV 9 ไฟล์จาก Kaggle\nวางใน datasets/"],
    ["Load", "dbt-duckdb ประกาศเป็น\nsource (external_location)"],
    ["Transform\n(Staging)", "stg_*.sql ดึงข้อมูล 1:1\n+ ingestion_timestamp"],
    ["Transform\n(Warehouse)", "สร้าง dim_*/fact_*\ndedupe + enrich + join"],
    ["Serve", "dev.duckdb → Streamlit\napp + dashboard"],
  ];
  const w = 2.15, gap = 0.3, startX = 0.6;
  steps.forEach(([title, desc], i) => {
    const x = startX + i * (w + gap);
    s.addShape(p.ShapeType.roundRect, { x, y: 2.2, w, h: 2.6, rectRadius: 0.08, fill: { color: i % 2 === 0 ? DEEP_BLUE : TEAL }, line: { width: 0 } });
    s.addText(String(i + 1), { x, y: 2.35, w, h: 0.5, isTextBox: true, margin: 0, align: "center", fontFace: "Cambria", fontSize: 22, bold: true, color: WHITE });
    s.addText(title, { x: x + 0.1, y: 2.9, w: w - 0.2, h: 0.6, isTextBox: true, margin: 0, align: "center", fontFace: "Calibri", fontSize: 13, bold: true, color: WHITE });
    s.addText(desc, { x: x + 0.1, y: 3.55, w: w - 0.2, h: 1.15, isTextBox: true, margin: 0, align: "center", fontFace: "Calibri", fontSize: 10.5, color: "EAF2F7" });
    if (i < steps.length - 1) {
      s.addText("→", { x: x + w, y: 3.2, w: gap, h: 0.5, isTextBox: true, margin: 0, align: "center", fontFace: "Arial", fontSize: 20, bold: true, color: MUTED });
    }
  });
  s.addText("dbt test ตรวจสอบคุณภาพข้อมูลทุกขั้นตอน (unique / not_null บน primary key ของแต่ละตาราง)", {
    x: 0.7, y: 5.3, w: 11.9, h: 0.5, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 12, italic: true, color: MUTED,
  });
}

function warehouseResultsSlide(p) {
  const s = p.addSlide();
  s.background = { color: WHITE };
  sectionHeader(s, "6. Data Warehouse Database — ผลลัพธ์");

  const stats = [
    ["16", "ตารางทั้งหมด"],
    ["9", "Staging Tables"],
    ["4 + 3", "Dimension + Fact Tables"],
    ["13 / 13", "dbt test ผ่านทั้งหมด"],
  ];
  let x = 0.7;
  stats.forEach(([num, label]) => {
    s.addShape(p.ShapeType.roundRect, { x, y: 2.0, w: 2.7, h: 2.0, rectRadius: 0.08, fill: { color: CARD_BG }, line: { color: "E1E7EC", width: 1 } });
    s.addText(num, { x, y: 2.2, w: 2.7, h: 0.9, isTextBox: true, margin: 0, align: "center", fontFace: "Cambria", fontSize: 34, bold: true, color: DEEP_BLUE });
    s.addText(label, { x, y: 3.15, w: 2.7, h: 0.6, isTextBox: true, margin: 0, align: "center", fontFace: "Calibri", fontSize: 13, color: MUTED });
    x += 2.9;
  });
  s.addText("ไฟล์ผลลัพธ์: olist_dw/dev.duckdb  •  สร้างจากคำสั่ง dbt run ภายในโฟลเดอร์ olist_dw/", {
    x: 0.7, y: 4.5, w: 11.9, h: 0.5, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 13, color: INK,
  });
}

function dashboardSlide(p) {
  const s = p.addSlide();
  s.background = { color: WHITE };
  sectionHeader(s, "7. Interactive Dashboard", "Streamlit + Altair — วิเคราะห์จาก fact_order_items join กับทุก dimension");

  const kpis = [
    ["R$ 13.4M", "Revenue"],
    ["97,277", "Orders"],
    ["R$ 137.88", "Avg Order Value"],
    ["12.4 วัน", "Avg Delivery Time"],
  ];
  let x = 0.7;
  kpis.forEach(([num, label]) => {
    s.addShape(p.ShapeType.roundRect, { x, y: 1.6, w: 2.7, h: 1.5, rectRadius: 0.08, fill: { color: NAVY }, line: { width: 0 } });
    s.addText(num, { x, y: 1.7, w: 2.7, h: 0.75, isTextBox: true, margin: 0, align: "center", fontFace: "Cambria", fontSize: 22, bold: true, color: WHITE });
    s.addText(label, { x, y: 2.45, w: 2.7, h: 0.5, isTextBox: true, margin: 0, align: "center", fontFace: "Calibri", fontSize: 12, color: "CADCFC" });
    x += 2.9;
  });

  s.addText("Top 3 หมวดหมู่สินค้าตามรายได้", { x: 0.7, y: 3.5, w: 5.6, h: 0.4, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 14, bold: true, color: TEAL });
  s.addText("1. health_beauty\n2. watches_gifts\n3. bed_bath_table", { x: 0.7, y: 3.95, w: 5.6, h: 1.4, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 13, color: INK, lineSpacingMultiple: 1.3 });

  s.addText("Top 3 รัฐลูกค้าตามรายได้", { x: 6.9, y: 3.5, w: 5.6, h: 0.4, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 14, bold: true, color: TEAL });
  s.addText("1. SP (São Paulo)\n2. RJ (Rio de Janeiro)\n3. MG (Minas Gerais)", { x: 6.9, y: 3.95, w: 5.6, h: 1.4, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 13, color: INK, lineSpacingMultiple: 1.3 });

  s.addText("ลิงก์ Web Application: miniproject-vvcre79hljddpvyj82zuub.streamlit.app", {
    x: 0.7, y: 5.7, w: 11.9, h: 0.5, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 12, italic: true, color: MUTED,
  });
}

function teamSlide(p) {
  const s = p.addSlide();
  s.background = { color: WHITE };
  sectionHeader(s, "8. Team Contribution");

  const members = [
    ["ชวนากร เพชรเจริญรัตน์", "chawanakorn-phet", "Data Modeling, dbt Pipeline, Dashboard"],
    ["กุลธิดา สมาขันธ์", "kunthida-samakhan", "Business Questions, Infographic"],
    ["วรวัฒน์ พรหมคุณ", "worawatpr-gh", "Data Model Diagram, Deployment"],
    ["เยี่ยมภพ ใบโพธิ์", "yiampopbaipo", "Dashboard, Presentation"],
  ];
  let y = 1.75;
  members.forEach(([name, gh, role]) => {
    s.addShape(p.ShapeType.roundRect, { x: 0.7, y, w: 11.9, h: 0.95, rectRadius: 0.06, fill: { color: CARD_BG }, line: { color: "E1E7EC", width: 1 } });
    s.addText(name, { x: 1.0, y: y + 0.1, w: 3.6, h: 0.4, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 14, bold: true, color: INK });
    s.addText("@" + gh, { x: 1.0, y: y + 0.5, w: 3.6, h: 0.35, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 11, color: MUTED });
    s.addText(role, { x: 4.8, y: y + 0.27, w: 7.5, h: 0.4, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 12.5, color: TEAL });
    y += 1.1;
  });
  s.addText("หลักฐานการทำงาน: Commit history และ GitHub Project board ที่ github.com/chawanakorn-phet/Mini_project", {
    x: 0.7, y: 6.0, w: 11.9, h: 0.5, isTextBox: true, margin: 0, fontFace: "Calibri", fontSize: 12, italic: true, color: MUTED,
  });
}

function closingSlide(p) {
  const s = p.addSlide();
  s.background = { color: NAVY };
  s.addText("ขอบคุณครับ", {
    x: 0.8, y: 2.8, w: 11.7, h: 1.0, isTextBox: true, margin: 0,
    fontFace: "Cambria", fontSize: 38, bold: true, color: WHITE,
  });
  s.addText("github.com/chawanakorn-phet/Mini_project", {
    x: 0.8, y: 3.75, w: 11.7, h: 0.5, isTextBox: true, margin: 0,
    fontFace: "Calibri", fontSize: 16, color: "CADCFC",
  });
}

const pres = newDeck();
titleSlide(pres);
operationalDbSlide(pres);
businessQuestionsSlide(pres, "2. Business Questions (1–8)", [
  "รายได้รวมและจำนวนออเดอร์เปลี่ยนแปลงอย่างไรในแต่ละเดือน/ไตรมาส/ปี?",
  "หมวดหมู่สินค้าใดสร้างรายได้สูงสุด 10 อันดับแรก?",
  "รัฐใดของลูกค้าสร้างรายได้และจำนวนออเดอร์มากที่สุด?",
  "มูลค่าออเดอร์เฉลี่ยแตกต่างกันอย่างไรในแต่ละรัฐ?",
  "ผู้ขายรายใดสร้างรายได้และจำนวนออเดอร์สูงสุด 10 อันดับแรก?",
  "ระยะเวลาจัดส่งเฉลี่ยเป็นเท่าไร และแตกต่างกันตามรัฐอย่างไร?",
  "ระยะเวลาจัดส่งมีความสัมพันธ์กับคะแนนรีวิวหรือไม่?",
  "คะแนนรีวิวเฉลี่ยของแต่ละหมวดหมู่สินค้าเป็นอย่างไร?",
], 0);
businessQuestionsSlide(pres, "2. Business Questions (9–15)", [
  "สัดส่วนวิธีการชำระเงินแต่ละประเภทเป็นอย่างไร?",
  "จำนวนงวดผ่อนชำระเฉลี่ยต่างกันอย่างไรในแต่ละวิธีชำระเงิน?",
  "หมวดหมู่ใดมีสัดส่วนค่าขนส่งต่อราคาสินค้าสูงที่สุด?",
  "มีรูปแบบตามฤดูกาลของยอดขายในแต่ละเดือนหรือไม่?",
  "ออเดอร์ที่จัดส่งล่าช้ากว่าประมาณการมีสัดส่วนเท่าไร กระจายตามรัฐอย่างไร?",
  "ออเดอร์ที่ได้คะแนนรีวิวต่ำ สัมพันธ์กับการจัดส่งล่าช้าหรือไม่?",
  "ลูกค้าที่ซื้อซ้ำมีสัดส่วนเท่าไรของยอดขายทั้งหมด?",
], 8);
dimensionsSlide(pres);
factsSlide(pres);
starSchemaSlide(pres);
etlSlide(pres);
warehouseResultsSlide(pres);
dashboardSlide(pres);
teamSlide(pres);
closingSlide(pres);

pres.writeFile({ fileName: "Mini_Project_Olist_DW.new.pptx" }).then(() => {
  console.log("done");
});
