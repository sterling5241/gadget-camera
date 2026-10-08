#!/bin/sh

# Installs the Gadget status card into an existing OctoEverywhere install.
# Usage: sh installer.sh [path to the octoeverywhere repo]

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

OE_DIR=$1
if [ -z "$OE_DIR" ]; then
    for dir in "$HOME/octoeverywhere" /usr/data/octoeverywhere /usr/share/octoeverywhere /mnt/UDISK/octoeverywhere; do
        if [ -f "$dir/moonraker_octoeverywhere/moonrakerhost.py" ]; then
            OE_DIR=$dir
            break
        fi
    done
fi

if [ -z "$OE_DIR" ] || [ ! -f "$OE_DIR/moonraker_octoeverywhere/moonrakerhost.py" ]; then
    echo "ERROR: OctoEverywhere was not found, pass the path to it, for example: sh installer.sh ~/octoeverywhere"
    exit 1
fi

echo "INFO: Installing the Gadget status card into $OE_DIR ..."
for file in moonraker_octoeverywhere/gadgetstatuscard.py moonraker_octoeverywhere/moonrakerhost.py linux_host/config.py octoeverywhere/gadget.py; do
    cp "$SCRIPT_DIR/$file" "$OE_DIR/$file" || exit $?
done

# turn the card on in every octoeverywhere.conf, the plugin keeps it next to moonraker.conf
# and a companion keeps it in its own data folder
found_config=false
for config in "$HOME"/printer_data*/config/octoeverywhere.conf /usr/data/printer_data/config/octoeverywhere.conf "$HOME"/.octoeverywhere-companion*/octoeverywhere.conf; do
    [ -f "$config" ] || continue
    found_config=true
    if grep -q "^status_card_enabled" "$config"; then
        sed -i 's/^status_card_enabled.*/status_card_enabled = true/' "$config"
    elif grep -q "^\[gadget\]" "$config"; then
        sed -i 's/^\[gadget\]/[gadget]\nstatus_card_enabled = true/' "$config"
    else
        printf '\n[gadget]\nstatus_card_enabled = true\n' >> "$config"
    fi
    echo "INFO: Enabled the Gadget status card in $config"
done

if [ "$found_config" != "true" ]; then
    echo "WARNING: No octoeverywhere.conf found, add this to it yourself:"
    echo "  [gadget]"
    echo "  status_card_enabled = true"
fi

echo "INFO: Restarting OctoEverywhere ..."
restarted=false
for service in /etc/init.d/S66octoeverywhere_service /etc/init.d/octoeverywhere_service; do
    if [ -f "$service" ]; then
        $service restart > /dev/null 2>&1
        restarted=true
    fi
done
if [ "$restarted" != "true" ] && command -v systemctl > /dev/null 2>&1; then
    for service in $(systemctl list-units --all --plain --no-legend "octoeverywhere*" 2> /dev/null | awk '{print $1}'); do
        sudo systemctl restart "$service"
        restarted=true
    done
fi
if [ "$restarted" != "true" ]; then
    echo "WARNING: Could not find the OctoEverywhere service, restart it yourself"
fi

echo
echo "Done! Now add a camera in Fluidd or Mainsail:"
echo "  Name:         Gadget"
echo "  Service:      MJPEG Adaptive"
echo "  Snapshot URL: /server/files/config/.octoeverywhere/gadget-status.svg"
echo "  Target FPS:   1"
echo
echo "Note: updating OctoEverywhere replaces these files, run this installer again afterwards."
