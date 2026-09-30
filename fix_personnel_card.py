"""Replace the static personnel card HTML with the dual-state allotted/not-allotted design."""
path = r'c:\Users\lotusone\Desktop\YAWAR\KOTE_NEW\templates\issuance_modal.html'

with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the range for the personnel card (Box B)
start_line = None
end_line = None
for i, line in enumerate(lines):
    if '<!-- Box B: Allotted Personnel Details -->' in line:
        start_line = i
    if start_line and i > start_line and '</div>' in line:
        # Count to find the closing tag of .detail-box-card
        # We need to find the one that matches Box B's opening div
        chunk = ''.join(lines[start_line:i+1])
        opens = chunk.count('<div')
        closes = chunk.count('</div>')
        if closes >= opens:
            end_line = i
            break

if start_line is None or end_line is None:
    print(f"ERROR: could not find range. start={start_line}, end={end_line}")
    # Print surrounding context for debugging
    for i, l in enumerate(lines[840:875], start=841):
        print(f"{i}: {repr(l)}")
    exit(1)

print(f"Replacing lines {start_line+1}–{end_line+1}")

new_card = '''                            <!-- Box B: Allotted Personnel Details -->
                            <div class="detail-box-card">
                                <div class="box-card-title">
                                    <i class="fa-solid fa-user-shield"></i> Allotted Personnel
                                </div>

                                <!-- NOT ALLOTTED STATE (shown when no person assigned) -->
                                <div id="notAllottedMsg" style="display: none; text-align: center; padding: 16px 10px;">
                                    <div style="font-size: 2rem; color: #cbd5e1; margin-bottom: 8px;"><i class="fa-solid fa-user-slash"></i></div>
                                    <div style="font-size: 0.82rem; font-weight: 800; color: #64748b;">Weapon Not Allotted Yet</div>
                                    <div style="font-size: 0.72rem; color: #94a3b8; margin-top: 3px; margin-bottom: 10px;">No personnel assigned in QM Stock.<br>Enter Army No. below to issue.</div>
                                    <div style="position: relative;">
                                        <input type="text" class="form-input" id="issuanceArmyNumber" placeholder="Enter Army No. to issue..." style="font-size: 0.82rem; font-weight: 700; height: 32px; padding: 4px 10px;" autocomplete="off">
                                        <div id="issuanceTroopSuggestions" class="suggestions-dropdown"></div>
                                    </div>
                                </div>

                                <!-- ALLOTTED STATE (shown when person is assigned) -->
                                <div id="allottedPersonnelDetails" style="display: none;">
                                    <div class="details-item">
                                        <span class="details-item__lbl">Army No.</span>
                                        <span class="details-item__val" id="scannedArmyNumber" style="font-family: monospace; font-weight: 800; color: #1e3a8a;">&mdash;</span>
                                    </div>
                                    <div class="details-item">
                                        <span class="details-item__lbl">Name</span>
                                        <span class="details-item__val" id="scannedTroopName">&mdash;</span>
                                    </div>
                                    <div class="details-item">
                                        <span class="details-item__lbl">Rank &amp; Co</span>
                                        <span class="details-item__val" id="scannedTroopRankCo">&mdash;</span>
                                    </div>
                                    <div class="details-item">
                                        <span class="details-item__lbl">Section</span>
                                        <span class="details-item__val" id="scannedTroopSec">&mdash;</span>
                                    </div>
                                </div>

                            </div>\n'''

new_lines = lines[:start_line] + [new_card] + lines[end_line+1:]

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"SUCCESS: Personnel card replaced (was lines {start_line+1}-{end_line+1})")
