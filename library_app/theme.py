"""三套皮肤：纸质档案 / 观察台 / 制图台。

所有颜色与字体集中在这里。标准控件由 build_qss() 的样式表驱动；
自绘控件（Logo、左侧功能轨、关系图、皮肤切换器）直接读取 Theme 字段。
"""
from __future__ import annotations

from dataclasses import dataclass
from string import Template


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    cn: str
    note: str
    is_dark: bool
    radius: int

    serif: str
    sans: str
    mono: str
    kai: str

    bg: str
    topbar: str
    rail: str
    panel: str
    panel_alt: str
    card: str
    card_hover: str
    canvas: str

    text: str
    text_dim: str
    muted: str
    faint: str

    line: str
    line_soft: str
    accent: str
    accent_deep: str
    on_accent: str
    accent_soft: str

    signal: str
    signal_soft: str
    danger: str

    mark_bg: str
    mark_text: str

    grid: str
    ring: str
    axis: str
    edge_struct: str
    edge_rec: str
    node_fill: str
    node_stroke: str
    node_id: str
    node_label: str
    center_fill: str
    center_id: str
    center_label: str

    meter_d: str
    meter_c: str
    meter_k: str
    scroll: str
    shadow: str
    row_hover: str


PAPER = Theme(
    key="paper",
    name="Paper Archive",
    cn="纸质档案",
    note="暖色、编辑排版、阅读优先",
    is_dark=False,
    radius=2,
    serif="SimSun",
    sans="Microsoft YaHei",
    mono="Consolas",
    kai="KaiTi",
    bg="#F2ECE1",
    topbar="#FBF7EF",
    rail="#F7F1E6",
    panel="#FBF7EF",
    panel_alt="#F7F1E6",
    card="#FCF8F1",
    card_hover="#FFFFFF",
    canvas="#F5EFE4",
    text="#241F1A",
    text_dim="#4A4238",
    muted="#6A5E4F",
    faint="#8A7D6B",
    line="#DED4C2",
    line_soft="#EAE2D3",
    accent="#A23E2A",
    accent_deep="#7E2C1C",
    on_accent="#FBF7EF",
    accent_soft="#F1DED5",
    signal="#4F6449",
    signal_soft="#E7EBE1",
    danger="#A23E2A",
    mark_bg="#EBC9B8",
    mark_text="#241F1A",
    grid="#EADFCD",
    ring="#D5C9B6",
    axis="#E0D4C1",
    edge_struct="#C9BBA5",
    edge_rec="#A23E2A",
    node_fill="#FBF7EF",
    node_stroke="#B9AB96",
    node_id="#5E5346",
    node_label="#3B342B",
    center_fill="#A23E2A",
    center_id="#FBF7EF",
    center_label="#241F1A",
    meter_d="#A23E2A",
    meter_c="#4F6449",
    meter_k="#B58A43",
    scroll="#D7CBB8",
    shadow="#3C2814",
    row_hover="#FFFDF8",
)

OBSERVATORY = Theme(
    key="observatory",
    name="Observatory",
    cn="观察台",
    note="深色仪器台、读数优先",
    is_dark=True,
    radius=2,
    serif="SimSun",
    sans="Microsoft YaHei",
    mono="Consolas",
    kai="KaiTi",
    bg="#070B0A",
    topbar="#090F0D",
    rail="#0B1210",
    panel="#0B1210",
    panel_alt="#0E1714",
    card="#0E1714",
    card_hover="#121E19",
    canvas="#080D0C",
    text="#DAE4DE",
    text_dim="#B7C6BF",
    muted="#A3B7AD",
    faint="#7E9287",
    line="#22332C",
    line_soft="#1A2721",
    accent="#E3B04B",
    accent_deep="#F1C46C",
    on_accent="#171208",
    accent_soft="#2B2517",
    signal="#58C9A3",
    signal_soft="#12261F",
    danger="#E07461",
    mark_bg="#3B2E16",
    mark_text="#F1C46C",
    grid="#142019",
    ring="#2C3E37",
    axis="#23352E",
    edge_struct="#4C6358",
    edge_rec="#E3B04B",
    node_fill="#0C1512",
    node_stroke="#455D52",
    node_id="#9AAFA4",
    node_label="#B9C8C1",
    center_fill="#E3B04B",
    center_id="#171208",
    center_label="#F1C46C",
    meter_d="#58C9A3",
    meter_c="#E3B04B",
    meter_k="#7FA9C9",
    scroll="#24352E",
    shadow="#000000",
    row_hover="#111C18",
)

DRAFTING = Theme(
    key="drafting",
    name="Drafting Table",
    cn="制图台",
    note="冷蓝制图、图谱常驻",
    is_dark=False,
    radius=0,
    serif="SimSun",
    sans="Microsoft YaHei",
    mono="Consolas",
    kai="KaiTi",
    bg="#E8EEF3",
    topbar="#FCFDFE",
    rail="#F7FAFC",
    panel="#FCFDFE",
    panel_alt="#F4F8FB",
    card="#FFFFFF",
    card_hover="#F4F8FB",
    canvas="#EDF3F7",
    text="#0E2334",
    text_dim="#31506A",
    muted="#556C7F",
    faint="#6D8497",
    line="#C7D5E1",
    line_soft="#DEE8EF",
    accent="#1D4ED8",
    accent_deep="#1439A8",
    on_accent="#FFFFFF",
    accent_soft="#E4ECFB",
    signal="#F05A28",
    signal_soft="#FCEAE3",
    danger="#F05A28",
    mark_bg="#FFD9CB",
    mark_text="#0E2334",
    grid="#DCE9F3",
    ring="#A9C0D4",
    axis="#B9CCDD",
    edge_struct="#9FB5C8",
    edge_rec="#F05A28",
    node_fill="#FFFFFF",
    node_stroke="#7E9CB5",
    node_id="#556C7F",
    node_label="#173B54",
    center_fill="#1D4ED8",
    center_id="#FFFFFF",
    center_label="#1439A8",
    meter_d="#1D4ED8",
    meter_c="#5C86C9",
    meter_k="#F05A28",
    scroll="#BCCDDB",
    shadow="#0E2334",
    row_hover="#F4F8FB",
)

THEMES: dict[str, Theme] = {
    "paper": PAPER,
    "observatory": OBSERVATORY,
    "drafting": DRAFTING,
}
THEME_ORDER = ["paper", "observatory", "drafting"]

QSS_TEMPLATE = Template(
    """
* { outline: none; }
QWidget {
    font-family: "$sans";
    font-size: 13px;
    color: $text;
}
QMainWindow, QWidget#Root { background: $bg; }

/* top bar */
QFrame#TopBar { background: $topbar; border-bottom: 1px solid $line; }
QLabel#BrandTitle { font-family: "$mono"; font-size: 14px; font-weight: 600; color: $text; }
QLabel#BrandCn { font-family: "$serif"; font-size: 14px; font-weight: 600; color: $text_dim; }
QLabel#BrandSub { font-family: "$mono"; font-size: 11px; color: $faint; }
QFrame#TopSearch { background: $card; border: 1px solid $line; border-radius: $radius; }
QLabel#SearchPrefix { font-family: "$mono"; font-size: 11px; color: $muted; border-right: 1px solid $line_soft; padding: 0 9px 0 10px; }
QLineEdit#SearchInput { background: transparent; border: none; color: $text; font-size: 14px; selection-background-color: $accent_soft; selection-color: $text; }
QPushButton#SearchButton { background: $accent; color: $on_accent; border: none; border-radius: $radius; font-family: "$mono"; font-size: 11px; padding: 0 12px; }
QPushButton#SearchButton:hover { background: $accent_deep; }
QLabel#TopStat { font-family: "$mono"; font-size: 12px; color: $muted; }
QFrame#ZoomBar { background: $card; border: 1px solid $line; border-radius: $radius; }
QPushButton#ZoomButton { background: transparent; border: none; color: $muted; font-family: "$mono"; font-size: 14px; padding: 0; }
QPushButton#ZoomButton:hover { color: $text; background: $accent_soft; }
QPushButton#ZoomValue { background: transparent; border: none; color: $text_dim; font-family: "$mono"; font-size: 11px; padding: 0; }
QPushButton#ZoomValue:hover { color: $accent; }
QPushButton#IssueButton { border: none; background: transparent; color: $danger; font-family: "$mono"; font-size: 12px; padding: 1px 0; }
QPushButton#IssueButton:hover { color: $text; }
QFrame#VLine { background: $line; border: none; }

/* rail */
QFrame#Rail { background: $rail; border-right: 1px solid $line; }
QLabel#RailFoot { font-family: "$mono"; font-size: 11px; color: $faint; }

/* panel */
QFrame#Panel { background: $panel; border-right: 1px solid $line; }
QFrame#PanelHead { background: $panel_alt; border-bottom: 1px solid $line; }
QLabel#PanelTitle { font-family: "$mono"; font-size: 11px; color: $text_dim; }
QLabel#PanelHint { font-family: "$mono"; font-size: 11px; color: $faint; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QLabel#SectionTitle { font-family: "$serif"; font-size: 14px; font-weight: 600; color: $text; }
QLabel#Kicker { font-family: "$mono"; font-size: 11px; color: $faint; }
QLabel#Note { font-size: 12px; color: $muted; background: transparent; border: none; }
QLabel#MonoMuted { font-family: "$mono"; font-size: 11px; color: $muted; }
QLabel#MonoFaint { font-family: "$mono"; font-size: 11px; color: $faint; }

/* cards */
QFrame#ResultCard, QFrame#RecCard, QFrame#DocRow {
    background: transparent;
    border: none;
    border-left: 2px solid transparent;
    border-bottom: 1px solid $line_soft;
    border-radius: 0px;
}
QFrame#ResultCard[hovered="true"], QFrame#RecCard[hovered="true"], QFrame#DocRow[hovered="true"] {
    background: $card_hover;
}
QFrame#ResultCard[active="true"] {
    background: $signal_soft;
    border-left-color: $signal;
}
QFrame#TreeRow {
    background: transparent;
    border-left: 2px solid transparent;
    border-radius: 0px;
}
QFrame#TreeRow[hovered="true"] { background: $row_hover; }
QFrame#TreeRow[kind="folder"][active="true"] { background: $accent_soft; border-left-color: $accent; }
QFrame#TreeRow[kind="doc"][active="true"] { background: $signal_soft; }
QFrame#CenterCard { background: $panel_alt; border: 1px solid $line; border-left: 3px solid $accent; border-radius: $radius; }
QFrame#Notice { background: $signal_soft; border: none; border-radius: $radius; }
QFrame#NoticeBar { background: $signal; border: none; }
QFrame#TimingCell { background: $card; border: 1px solid $line; border-radius: $radius; }
QFrame#TimingCell[active="true"] { background: $accent_soft; border-color: $accent; }
QFrame#TreeScroll { background: transparent; border: none; border-bottom: 1px solid $line; }

QLabel#RowTitle { font-family: "$serif"; font-size: 14px; font-weight: 600; color: $text; }
QLabel#RowPath { font-family: "$mono"; font-size: 11px; color: $faint; }
QLabel#Snippet { font-size: 12px; color: $muted; }
QLabel#Reason { font-size: 12px; color: $muted; }
QLabel#HitBadge { font-family: "$mono"; font-size: 11px; color: $muted; border: 1px solid $line; padding: 1px 4px; }
QLabel#RecTotal { font-family: "$mono"; font-size: 16px; color: $accent; }
QLabel#ScoreKey { font-family: "$kai"; font-size: 12px; color: $faint; }
QLabel#Chips { font-size: 11px; color: $text_dim; }
QLabel#TimingLabel { font-family: "$mono"; font-size: 11px; color: $faint; }
QLabel#TimingValue { font-family: "$mono"; font-size: 14px; color: $text_dim; }
QFrame#TimingCell[active="true"] QLabel#TimingValue { color: $accent; }
QLabel#TimingUnit { font-family: "$mono"; font-size: 11px; color: $muted; }
QLabel#ScopeName { font-size: 12px; color: $muted; }
QLabel#FreqFoot { font-family: "$mono"; font-size: 11px; color: $faint; }
QLabel#FreqOK { font-family: "$mono"; font-size: 11px; color: $signal; }
QLabel#AlgoName { font-family: "$mono"; font-size: 11px; color: $muted; }

/* tree */
QLabel#TreeName { font-size: 13px; color: $text_dim; }
QLabel#TreeCount { font-family: "$mono"; font-size: 11px; color: $faint; }
QFrame#TreeRow[kind="folder"] QLabel#TreeName { font-weight: 600; }
QFrame#TreeRow[kind="folder"][active="true"] QLabel#TreeName { color: $accent_deep; }
QFrame#TreeRow[kind="doc"][active="true"] QLabel#TreeName { color: $signal; }
QLabel#Dot { font-family: "$mono"; font-size: 12px; color: $faint; }
QToolButton#Caret { background: transparent; border: none; color: $faint; font-family: "$mono"; font-size: 11px; padding: 0; }
QToolButton#Caret:hover { color: $text; }

/* segments */
QPushButton#Segment {
    background: transparent;
    border: 1px solid $line;
    border-radius: $radius;
    color: $muted;
    font-family: "$mono";
    font-size: 11px;
    padding: 5px 8px;
}
QPushButton#Segment:hover { border-color: $accent; color: $text; }
QPushButton#Segment:checked { background: $accent; border-color: $accent; color: $on_accent; }
QPushButton#Ghost { background: transparent; border: none; color: $muted; font-family: "$mono"; font-size: 11px; padding: 3px 0; }
QPushButton#Ghost:hover { color: $text; }
QPushButton#Primary { background: transparent; border: none; color: $accent; font-family: "$mono"; font-size: 11px; padding: 3px 0; }
QPushButton#Primary:hover { color: $accent_deep; }
QPushButton#CloseButton { background: transparent; border: none; color: $muted; font-family: "$mono"; font-size: 15px; }
QPushButton#CloseButton:hover { background: $line_soft; color: $text; }

/* empty */
QLabel#EmptyGlyph { font-family: "$mono"; font-size: 28px; color: $line; }
QLabel#EmptyTitle { font-size: 13px; color: $muted; }
QLabel#EmptyHint { font-size: 12px; color: $faint; }

/* bars / meters */
QProgressBar { background: $line_soft; border: none; border-radius: 2px; }
QProgressBar::chunk { background: $accent; border-radius: 2px; }
QProgressBar#BarHot::chunk { background: $accent; }
QProgressBar#Bar::chunk { background: $text_dim; }
QProgressBar#MeterD::chunk { background: $meter_d; }
QProgressBar#MeterC::chunk { background: $meter_c; }
QProgressBar#MeterK::chunk { background: $meter_k; }

/* canvas */
QWidget#CanvasArea { background: $canvas; }
QFrame#MapHead { background: transparent; border-bottom: 1px solid $line; }
QLabel#MapKicker { font-family: "$mono"; font-size: 11px; color: $muted; }
QLabel#MapTitle { font-family: "$serif"; font-size: 19px; font-weight: 600; color: $text; }
QLabel#MapTitleEn { font-family: "$mono"; font-size: 11px; color: $faint; }
QLabel#MapCenter { font-size: 12px; color: $muted; }
QFrame#KickLine { background: $signal; border: none; }
QFrame#StatsBox { background: $card; border: 1px solid $line; border-radius: $radius; }
QFrame#StatCell { background: transparent; border-right: 1px solid $line_soft; }
QLabel#StatLabel { font-family: "$mono"; font-size: 11px; color: $faint; }
QLabel#StatValue { font-family: "$mono"; font-size: 14px; color: $text; }
QLabel#StatValueHot { font-family: "$mono"; font-size: 14px; color: $signal; }

/* doc panel */
QFrame#DocPanel { background: $panel; border-left: 1px solid $line; }
QFrame#DocHead { background: $panel_alt; border-bottom: 1px solid $line; }
QLabel#DocLabel { font-family: "$mono"; font-size: 11px; color: $muted; }
QLabel#DocLabelStrong { font-family: "$mono"; font-size: 11px; color: $text; }
QLabel#CenterBadge { font-family: "$mono"; font-size: 11px; color: $accent; }
QTextBrowser#DocText {
    background: $panel;
    border: none;
    color: $text;
    selection-background-color: $accent_soft;
    selection-color: $text;
}
QTextBrowser#DocText QScrollBar:vertical { background: transparent; }

/* status */
QFrame#StatusBar { background: $panel_alt; border-top: 1px solid $line; }
QLabel#StatusText { font-family: "$mono"; font-size: 11px; color: $faint; }

/* issue */
QFrame#IssuePopup { background: $panel; border: 1px solid $line; }
QLabel#IssueTitle { font-family: "$mono"; font-size: 11px; color: $text_dim; }
QLabel#IssueFile { font-family: "$mono"; font-size: 12px; color: $accent; }
QLabel#IssueText { font-size: 12px; color: $muted; }

/* scrollbars / tooltips */
QScrollBar:vertical { background: transparent; width: 9px; margin: 0; }
QScrollBar::handle:vertical { background: $scroll; min-height: 22px; border-radius: 4px; }
QScrollBar::handle:vertical:hover { background: $muted; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 9px; }
QScrollBar::handle:horizontal { background: $scroll; min-width: 22px; border-radius: 4px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QToolTip { background: $card; color: $text; border: 1px solid $line; padding: 4px 6px; font-size: 12px; }

/* workspace views */
QFrame#ViewHead { background: transparent; border-bottom: 1px solid $line; }
QLabel#ViewTitle { font-family: "$serif"; font-size: 20px; font-weight: 600; color: $text; }
QLabel#ViewSub { font-family: "$mono"; font-size: 11px; color: $muted; }
QLabel#DemoBadge { font-family: "$mono"; font-size: 10px; color: $accent; border: 1px solid $accent; border-radius: $radius; padding: 1px 6px; }
QPushButton#LinkButton { background: transparent; border: none; color: $accent; font-family: "$mono"; font-size: 11px; padding: 2px 0; }
QPushButton#LinkButton:hover { color: $accent_deep; }
QFrame#AlgoCard, QFrame#Card { background: $card; border: 1px solid $line; border-radius: $radius; }
QLabel#AlgoTitle { font-family: "$mono"; font-size: 11px; color: $text_dim; }
QLabel#AlgoLine { font-family: "$mono"; font-size: 10px; color: $muted; }
QLabel#AlgoStep { font-family: "$mono"; font-size: 10px; color: $text_dim; }
QFrame#DocBar { background: $panel_alt; border-bottom: 1px solid $line; }
    """
)


def build_qss(theme: Theme) -> str:
    return QSS_TEMPLATE.substitute(
        sans=theme.sans,
        serif=theme.serif,
        mono=theme.mono,
        kai=theme.kai,
        radius=str(theme.radius),
        bg=theme.bg,
        topbar=theme.topbar,
        rail=theme.rail,
        panel=theme.panel,
        panel_alt=theme.panel_alt,
        card=theme.card,
        card_hover=theme.card_hover,
        canvas=theme.canvas,
        text=theme.text,
        text_dim=theme.text_dim,
        muted=theme.muted,
        faint=theme.faint,
        line=theme.line,
        line_soft=theme.line_soft,
        accent=theme.accent,
        accent_deep=theme.accent_deep,
        on_accent=theme.on_accent,
        accent_soft=theme.accent_soft,
        signal=theme.signal,
        signal_soft=theme.signal_soft,
        danger=theme.danger,
        mark_bg=theme.mark_bg,
        mark_text=theme.mark_text,
        grid=theme.grid,
        ring=theme.ring,
        axis=theme.axis,
        edge_struct=theme.edge_struct,
        edge_rec=theme.edge_rec,
        node_fill=theme.node_fill,
        node_stroke=theme.node_stroke,
        node_id=theme.node_id,
        node_label=theme.node_label,
        center_fill=theme.center_fill,
        center_id=theme.center_id,
        center_label=theme.center_label,
        meter_d=theme.meter_d,
        meter_c=theme.meter_c,
        meter_k=theme.meter_k,
        scroll=theme.scroll,
        shadow=theme.shadow,
        row_hover=theme.row_hover,
    )
