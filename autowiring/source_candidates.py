"""Curated discovery leads, NOT a list of files downloaded or licensed for training.

Research verified on 2026-11-16. A public URL is not a license to store,
redistribute or use a document to train a model. Keep rights and applicability
distinct from format and technical relevance.
"""
CANDIDATES=[
 {
  "id":"swift2007_demo",
  "title":"Suzuki Swift 2007-2011 colored wiring diagrams — publisher demo",
  "url":"https://krutilvertel.com/pdf/demo/motorist/electrochemi-suzuki-swift-2007-demo.pdf",
  "format":"pdf","vehicle":"Suzuki Swift 2007–2011",
  "systems":["symbols","wire_color_legend","junction_block","connector_layout","keyless_start"],
  "source":"KrutilVertel / Motorist",
  "availability":"public_preview_link_found",
  "rights":"publisher_copyright; preview accessible, local archival/training permission unverified",
  "archive_status":"requires_rights_review",
  "notes":"Public sample only; not the 388-page full manual. Variant and market applicability must be checked."
 },
 {
  "id":"swift2007_full_workshop",
  "title":"Suzuki Swift 2007 2.G Service Workshop Manual (1496 pages)",
  "url":"https://www.carmanualsonline.info/suzuki-swift-2007-2-g-service-workshop-manual/",
  "format":"html_manual_viewer","vehicle":"Suzuki Swift 2007 2.G",
  "systems":["connector_layout","ground_points","junction_block","system_circuit","troubleshooting"],
  "source":"CarManualsOnline",
  "availability":"online_viewer_found",
  "rights":"copyright/licensing not verified",
  "archive_status":"link_only",
  "notes":"Web page indicates 1496 pages and ~34.44 MB PDF; no direct PDF download was verified. No automated page scraping."
 },
 {
  "id":"swift2007_paid",
  "title":"Suzuki Swift 2007-2011 colored wiring diagrams (full 388-page book)",
  "url":"https://krutilvertel.com/en/catalogue/suzuki/electrochemi-suzuki-swift-2007",
  "format":"paid_pdf","vehicle":"Suzuki Swift 2007–2011",
  "systems":["power_distribution","starting","charging","cooling_fan","connector_list"],
  "source":"KrutilVertel / Motorist",
  "availability":"purchase_required",
  "rights":"copyrighted commercial manual; purchase/license required",
  "archive_status":"purchase_or_permission_required",
  "notes":"Do not attempt to bypass payment or scrape the full paid book."
 },
 {
  "id":"bmw_etm_archive",
  "title":"BMW Electrical Troubleshooting Manuals archive index",
  "url":"https://shark.armchair.mb.ca/~dave/BMW/",
  "format":"html_directory_unverified","vehicle":"BMW E23/E28/E30/E31/E32/E34 and others",
  "systems":["electrical_troubleshooting_manual"],
  "source":"BMW ETM historical mirror",
  "availability":"index_reported_but_unreachable_in_research_environment",
  "rights":"historical mirror; redistribution/training rights unverified",
  "archive_status":"link_only",
  "notes":"Index URL was supplied by the user. Exact downloadable PDF URLs could not be confirmed; do not claim collected."
 },
 {
  "id":"bmw_e36_etm_1997",
  "title":"BMW E36 1997 US/Canada ETM (historical link reference)",
  "url":"https://www.bimmernut.com/t/all-us-e36-etms/38999",
  "format":"forum_link_index","vehicle":"BMW E36 1997 US/Canada",
  "systems":["electrical_troubleshooting_manual"],
  "source":"BimmerNut forum referencing BMW technical information",
  "availability":"historical_link_reported_not_pdf_verified",
  "rights":"BMW manual rights unverified",
  "archive_status":"link_only",
  "notes":"Forum lists e36_97.pdf as historical BMWTechInfo path; US/Canada diagrams may differ from Indonesia."
 },
 {
  "id":"subaru_crosstrek_phev_2021",
  "title":"Subaru Crosstrek PHEV 2019-2021 DTC P0452 service bulletin",
  "url":"https://static.nhtsa.gov/odi/tsbs/2024/MC-10249599-0001.pdf",
  "format":"pdf","vehicle":"Subaru Crosstrek PHEV 2019–2021",
  "systems":["sensor_pinout","ecm","dtc_diagnostic_flow"],
  "source":"NHTSA-hosted Subaru service bulletin 09-82-23R",
  "availability":"public_pdf_link_found",
  "rights":"© Subaru of America, all rights reserved",
  "archive_status":"link_only",
  "notes":"Useful reference for evidence-driven diagnosis; do not bulk archive or train without rights review."
 },
 {
  "id":"ram1500_dual_battery_2025",
  "title":"RAM 1500 2025 dual-battery grounding and 150A fuse diagram",
  "url":"https://static.nhtsa.gov/odi/tsbs/2024/MC-11007076-0001.pdf",
  "format":"pdf","vehicle":"RAM 1500 DT 2025",
  "systems":["dual_battery","power_distribution","ground","fuse"],
  "source":"NHTSA-hosted Stellantis warranty newsletter",
  "availability":"public_pdf_link_found",
  "rights":"manufacturer content; reuse/training permission unverified",
  "archive_status":"link_only",
  "notes":"Diagram is embedded in a newsletter, not a complete wiring manual."
 },
 {
  "id":"bendix_blindspotter",
  "title":"Bendix BlindSpotter Side Object Detection Service Data",
  "url":"https://static.nhtsa.gov/odi/tsbs/2021/MC-10206138-0001.pdf",
  "format":"pdf","vehicle":"Commercial truck/bus sensor system",
  "systems":["diagnostic_flow","connector_pinout","12v_24v_power","ground"],
  "source":"NHTSA-hosted Bendix service data SD-61-4933",
  "availability":"public_pdf_link_found",
  "rights":"manufacturer service material; reuse/training permission unverified",
  "archive_status":"link_only",
  "notes":"Diagnostic examples only; not Suzuki/BMW-specific."
 },
 {
  "id":"audi_a6_steering_tsb",
  "title":"Audi A6/A7 2019-2022 steering connector corrosion TSB",
  "url":"https://static.nhtsa.gov/odi/tsbs/2022/MC-10207164-0001.pdf",
  "format":"pdf","vehicle":"Audi A6/A7 family 2019–2022",
  "systems":["power_steering","connector_corrosion","repair"],
  "source":"NHTSA-hosted Audi TSB 94 22 55",
  "availability":"public_pdf_link_found",
  "rights":"explicit publisher restriction on copying/storing without permission",
  "archive_status":"link_only_no_archive",
  "notes":"Bulletin expressly prohibits storing in retrieval systems without prior permission. Do not import into AutoWiring library."
 }
]
def candidates():
    return [dict(x) for x in CANDIDATES]
