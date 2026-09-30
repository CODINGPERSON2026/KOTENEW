#!/usr/bin/env python3
"""Fix issuance_modal.html: merge slides 2 & 3 into one combined slide."""

path = r'c:\Users\lotusone\Desktop\YAWAR\KOTE_NEW\templates\issuance_modal.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find start of old slide 2
marker_start = '<!-- ═══ SLIDE 2: SCANNED RESULTS & DETAILS ═══ -->'
# Find end of old slide 3 closing + slider closing
marker_end = '</div><!-- /stage-slider-track -->\n                        </div><!-- /stage-slider-viewport -->\n\n            </div>'

idx_start = content.find(marker_start)
idx_end = content.find(marker_end)

if idx_start == -1:
    print("ERROR: Could not find start marker. Searching alternatives...")
    # Try finding via partial
    for s in ['SLIDE 2:', 'scannedWeaponResultView', 'stage-slide']:
        i = content.find(s)
        print(f"  '{s}' found at index {i}: {repr(content[i:i+60])}")
    exit(1)

if idx_end == -1:
    print("ERROR: Could not find end marker.")
    # Show what we have near the end
    alt = content.find('/stage-slider-viewport')
    print(f"  '/stage-slider-viewport' at {alt}: {repr(content[alt-30:alt+50])}")
    exit(1)

print(f"Start marker found at: {idx_start}")
print(f"End marker found at: {idx_end}")
print("Start context:", repr(content[idx_start:idx_start+80]))
print("End context:", repr(content[idx_end:idx_end+80]))

new_slide2 = '''<!-- ═══ SLIDE 2: DETAILS + FINGERPRINT MERGED ═══ -->
                <div class="stage-slide">
                <div id="scannedWeaponResultView" style="padding: 2px 0;">

                    <!-- Top Status Banner + Rescan -->
                    <div class="result-top-bar" style="margin-bottom: 10px;">
                        <div id="currentWeaponStatusBanner" class="weapon-status-banner status-banner--in">
                            <i class="fa-solid fa-warehouse"></i> CURRENT STATUS: <strong id="statusBannerText">IN KOTE ARMORY (AVAILABLE)</strong>
                        </div>
                        <button type="button" class="rescan-btn" onclick="resetToFullScanner()">
                            <i class="fa-solid fa-barcode"></i> Scan Another
                        </button>
                    </div>

                    <!-- 2-Column Layout: Left = Info Cards, Right = Fingerprint + Execute -->
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; align-items: start;">

                        <!-- LEFT COLUMN: Weapon + Personnel Cards -->
                        <div style="display: flex; flex-direction: column; gap: 10px;">

                            <!-- Weapon Details Card -->
                            <div class="detail-box-card">
                                <div class="box-card-title"><i class="fa-solid fa-gun"></i> Weapon Details</div>
                                <div class="details-item">
                                    <span class="details-item__lbl">Type</span>
                                    <span class="details-item__val" id="scannedWeaponType" style="color: #1e3a8a;">&#x2014;</span>
                                </div>
                                <div class="details-item">
                                    <span class="details-item__lbl">Butt No.</span>
                                    <span class="details-item__val" id="scannedButtNumber">&#x2014;</span>
                                </div>
                                <div class="details-item">
                                    <span class="details-item__lbl">Register No.</span>
                                    <span class="details-item__val" id="scannedRegisterNumber" style="font-family: monospace;">&#x2014;</span>
                                </div>
                            </div>

                            <!-- Personnel Details Card -->
                            <div class="detail-box-card">
                                <div class="box-card-title"><i class="fa-solid fa-user-shield"></i> Allotted Personnel</div>
                                <div class="details-item" style="position: relative;">
                                    <span class="details-item__lbl">Army No.</span>
                                    <div style="position: relative; width: 58%;">
                                        <input type="text" class="form-input" id="issuanceArmyNumber" placeholder="Enter Army No..." style="font-size: 0.8rem; font-weight: 700; height: 28px; padding: 2px 8px;" autocomplete="off">
                                        <div id="issuanceTroopSuggestions" class="suggestions-dropdown"></div>
                                    </div>
                                </div>
                                <div class="details-item">
                                    <span class="details-item__lbl">Name</span>
                                    <span class="details-item__val" id="scannedTroopName">&#x2014;</span>
                                </div>
                                <div class="details-item">
                                    <span class="details-item__lbl">Rank &amp; Co</span>
                                    <span class="details-item__val" id="scannedTroopRankCo">&#x2014;</span>
                                </div>
                                <div class="details-item">
                                    <span class="details-item__lbl">Section</span>
                                    <span class="details-item__val" id="scannedTroopSec">&#x2014;</span>
                                </div>
                            </div>

                        </div><!-- /left column -->

                        <!-- RIGHT COLUMN: Purpose + Fingerprint + Execute -->
                        <div style="display: flex; flex-direction: column; gap: 10px;">

                            <!-- Purpose & Duty (OUT mode only) -->
                            <div id="purposeDutyGroup" class="detail-box-card">
                                <div class="box-card-title"><i class="fa-solid fa-map-pin"></i> Purpose &amp; Duty Location</div>
                                <div style="display: flex; flex-direction: column; gap: 6px;">
                                    <div>
                                        <span style="font-size: 0.68rem; color: #64748b; font-weight: 700; text-transform: uppercase;">Purpose</span>
                                        <select class="form-input" id="issuancePurposeSelect" style="font-weight: 700; font-size: 0.8rem; height: 32px; margin-top: 2px;">
                                            <option value="DUTY" selected>DUTY</option>
                                            <option value="RP">RP</option>
                                            <option value="POST">POST</option>
                                            <option value="DET">DET</option>
                                            <option value="TD">TD</option>
                                            <option value="TRAINING">TRAINING</option>
                                            <option value="FIRING RANGE">FIRING RANGE</option>
                                            <option value="MAINTENANCE">MAINTENANCE</option>
                                            <option value="OPERATION">OPERATION / MOVEMENT</option>
                                            <option value="INSPECTION">INSPECTION</option>
                                        </select>
                                    </div>
                                    <div>
                                        <span style="font-size: 0.68rem; color: #64748b; font-weight: 700; text-transform: uppercase;">Duty Location</span>
                                        <select class="form-input" id="issuanceDutySelect" style="font-weight: 700; font-size: 0.8rem; height: 32px; margin-top: 2px;">
                                            <option value="MAIN GATE">MAIN GATE</option>
                                            <option value="RP">RP</option>
                                            <option value="SIGNAL CENT">SIGNAL CENT</option>
                                            <option value="JCO MESS GATE">JCO MESS GATE</option>
                                            <option value="QUATER GUARD">QUATER GUARD</option>
                                            <option value="KOTE PQT">KOTE PQT</option>
                                            <option value="QRT">QRT (QUICK REACTION TEAM)</option>
                                            <option value="PATROL">PATROL / NIGHT WATCH</option>
                                            <option value="ESCORT">CONVOY / ESCORT DUTY</option>
                                            <option value="GENERAL DUTY">GENERAL DUTY</option>
                                            <option value="OTHER">OTHER (Specify...)</option>
                                        </select>
                                        <div id="issuanceDutyCustomWrapper" style="display: none; margin-top: 4px;">
                                            <input type="text" class="form-input" id="issuanceDutyCustomInput" placeholder="Specify custom Duty..." style="font-weight: 700; font-size: 0.8rem; height: 30px;">
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <!-- Multi-Weapon Rule Note -->
                            <div id="weaponLimitRuleNote" style="font-size: 0.72rem; font-weight: 700; color: #0284c7; background: #e0f2fe; border: 1px solid #7dd3fc; border-radius: 6px; padding: 4px 8px; display: none;">
                                <i class="fa-solid fa-circle-info"></i> <span id="weaponLimitRuleText">Single weapon limit applies for Jawans.</span>
                            </div>

                            <!-- HID Hardware Status -->
                            <div style="background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 6px 12px; display: flex; align-items: center; justify-content: space-between;">
                                <div style="display: flex; align-items: center; gap: 8px; font-size: 0.75rem; font-weight: 700; color: #0f172a;">
                                    <i class="fa-solid fa-microchip" style="color: #1e3a8a;"></i>
                                    <span id="hidDeviceNameText">HID DigitalPersona 4500</span>
                                </div>
                                <span id="hidDeviceStatusBadge" style="font-size: 0.7rem; font-weight: 700; padding: 2px 8px; border-radius: 10px; background: #fffbeb; color: #b45309; border: 1px solid #fde68a;">Checking...</span>
                            </div>

                            <!-- Fingerprint Scanner Box -->
                            <div class="biometric-scanner-box">
                                <div class="fingerprint-icon-wrapper" id="fingerprintWrapper">
                                    <i class="fa-solid fa-fingerprint"></i>
                                </div>
                                <span class="biometric-status-text" id="biometricStatusText">Tap to Scan Fingerprint</span>
                                <div style="display: flex; gap: 6px; margin-top: 4px;">
                                    <button type="button" class="qm-btn qm-btn--secondary" id="pairHidDeviceBtn" style="font-size: 0.74rem; padding: 3px 8px; background: #ffffff; border-color: #cbd5e1;" title="Pair HID 4500 USB">
                                        <i class="fa-solid fa-usb" style="color: #1e3a8a;"></i> Pair USB
                                    </button>
                                    <button type="button" class="qm-btn qm-btn--secondary" id="triggerBiometricBtn" style="font-size: 0.74rem; padding: 3px 8px; background: #ffffff; border-color: #cbd5e1;">
                                        <i class="fa-solid fa-fingerprint" style="color: #059669;"></i> Scan
                                    </button>
                                    <button type="button" class="qm-btn qm-btn--secondary" id="hidTroubleshootBtn" style="font-size: 0.74rem; padding: 3px 8px; background: #ffffff; border-color: #cbd5e1;" title="HID Setup">
                                        <i class="fa-solid fa-circle-question" style="color: #d97706;"></i>
                                    </button>
                                </div>
                            </div>

                            <!-- Live Timestamp -->
                            <div style="display: flex; align-items: center; justify-content: space-between; font-size: 0.73rem; font-weight: 600; color: #64748b; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 7px; padding: 5px 10px;">
                                <span><i class="fa-solid fa-clock"></i> Timestamp</span>
                                <span id="liveTimestampBadge" style="font-weight: 700; color: #0f172a; font-family: monospace;">--:--:--</span>
                            </div>

                            <!-- Execute Button -->
                            <button type="button" class="btn-action-out" id="executeIssuanceBtn">
                                <i class="fa-solid fa-arrow-right-from-bracket"></i>
                                <span>CONFIRM &amp; EXECUTE WEAPON OUT</span>
                            </button>

                        </div><!-- /right column -->
                    </div><!-- /grid -->

                </div><!-- /scannedWeaponResultView -->
                </div><!-- /stage-slide 2 -->

                </div><!-- /stage-slider-track -->
                </div><!-- /stage-slider-viewport -->

            </div>'''

old_section = content[idx_start: idx_end + len(marker_end)]
new_content = content[:idx_start] + new_slide2 + content[idx_end + len(marker_end):]

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("SUCCESS: File updated.")
print(f"Replaced {len(old_section)} chars with {len(new_slide2)} chars")
