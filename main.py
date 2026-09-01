from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QSpinBox,
    QPushButton, QAction, QCheckBox, QHBoxLayout,
    QComboBox
)
from qgis.PyQt.QtCore import QTimer
from qgis.core import QgsFeatureRequest, NULL


class MultiNestingNumbering:

    FIELD_NAME = "od_numb"

    def __init__(self, iface):
        self.iface = iface
        self.dock_widget = None
        self.action = None

        # Debounce timer (not strictly needed with dropdown, but harmless)
        self._prefix_timer = QTimer()
        self._prefix_timer.setSingleShot(True)
        self._prefix_timer.timeout.connect(self.update_next_number)

    def initGui(self):
        self.action = QAction("Αρίθμηση Οδικών Κλάδων", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu("Αρίθμηση Οδικών Κλάδων", self.action)
        self.iface.addToolBarIcon(self.action)

        # Optional: refresh next number if user changes active layer while dock is open
        self.iface.currentLayerChanged.connect(self.on_current_layer_changed)

    def unload(self):
        self.iface.removePluginMenu("Αρίθμηση Οδικών Κλάδων", self.action)
        self.iface.removeToolBarIcon(self.action)
        try:
            self.iface.currentLayerChanged.disconnect(self.on_current_layer_changed)
        except Exception:
            pass

    def on_current_layer_changed(self, layer):
        if self.dock_widget and self.dock_widget.isVisible():
            self.update_next_number()

    def get_target_layer(self):
        layer = self.iface.activeLayer()
        if not layer:
            self.iface.messageBar().pushWarning("Layer", "Δεν υπάρχει ενεργό layer.")
            return None

        # 1 = line geometry
        if layer.geometryType() != 1:
            self.iface.messageBar().pushWarning("Layer", "Επίλεξε γραμμικό layer.")
            return None

        # must be editable (your requirement)
        if not layer.isEditable():
            self.iface.messageBar().pushWarning("Edit mode", "Κάνε το layer editable (Toggle Editing).")
            return None

        idx = layer.fields().indexFromName(self.FIELD_NAME)
        if idx < 0:
            self.iface.messageBar().pushWarning(
                "Field",
                f"Το πεδίο '{self.FIELD_NAME}' δεν υπάρχει στο layer."
            )
            return None

        return layer

    def run(self):
        if not self.dock_widget:
            self.dock_widget = QWidget()
            self.dock_widget.setWindowTitle("Αρίθμηση Οδικών Κλάδων")
            self.dock_widget.setStyleSheet("background-color: white; color: black;")
            layout = QVBoxLayout()

            # Next value
            row1 = QHBoxLayout()
            self.cb_next = QCheckBox("Επόμενη Τιμή")
            self.next_spin = QSpinBox()
            self.next_spin.setMinimum(0)
            self.next_spin.setMaximum(999999)
            self.next_spin.setReadOnly(True)
            row1.addWidget(self.cb_next)
            row1.addWidget(self.next_spin)
            layout.addLayout(row1)

            # Manual value
            row2 = QHBoxLayout()
            self.cb_manual = QCheckBox("Επεξεργασία Τιμής")
            self.manual_spin = QSpinBox()
            self.manual_spin.setMinimum(0)
            self.manual_spin.setMaximum(999999)
            row2.addWidget(self.cb_manual)
            row2.addWidget(self.manual_spin)
            layout.addLayout(row2)

            # Make checkboxes mutually exclusive
            self.cb_next.toggled.connect(
                lambda checked: self.cb_manual.setChecked(False) if checked else None
            )
            self.cb_manual.toggled.connect(
                lambda checked: self.cb_next.setChecked(False) if checked else None
            )

            # Prefix dropdown
            row3 = QHBoxLayout()
            self.prefix_label = QLabel("Μεταβλητή τιμή Δημοτικής Ενότητας")
            self.prefix_dropdown = QComboBox()

            prefixes = [
                "a","b","c","d","e","f","g","h","i","j","k","l","m","n","o","p","q","r","s","t","u","v","w","x","y","z",
                "aa","bb","cc","dd","ee","ff","gg","hh","ii","kk","mm","nn","oo","pp",
                "aaa","bbb","ccc","ddd","eee","fff","ggg","hhh","iii","kkk","mmm","nnn","ooo","ppp","qqq","rrrr","sss","ttt","uuu","xxx"
            ]
            self.prefix_dropdown.addItems(prefixes)
            self.prefix_dropdown.setEditable(False)

            row3.addWidget(self.prefix_label)
            row3.addWidget(self.prefix_dropdown)
            layout.addLayout(row3)

            self.prefix_dropdown.currentTextChanged.connect(lambda _: self.update_next_number())

            # Buttons
            self.add_btn = QPushButton("Προσθήκη")
            self.del_btn = QPushButton("Διαγραφή")
            self.add_btn.clicked.connect(self.apply_number)
            self.del_btn.clicked.connect(self.delete_manual_number)
            layout.addWidget(self.add_btn)
            layout.addWidget(self.del_btn)

            self.dock_widget.setLayout(layout)

        self.update_next_number()
        self.dock_widget.show()

    def get_prefix(self):
        return self.prefix_dropdown.currentText().strip() if hasattr(self, "prefix_dropdown") else ""

    def get_used_numbers(self):
        """Read-only scan of used numbers for current prefix in od_numb."""
        layer = self.iface.activeLayer()
        used = set()
        if not layer:
            return used

        if layer.geometryType() != 1:
            return used

        field_name = self.FIELD_NAME
        if layer.fields().indexFromName(field_name) < 0:
            return used

        prefix = self.get_prefix()

        req = QgsFeatureRequest()
        req.setFlags(req.flags() | QgsFeatureRequest.NoGeometry)
        req.setSubsetOfAttributes([field_name], layer.fields())

        if prefix:
            p = prefix.replace("'", "''")
            req.setFilterExpression(f"\"{field_name}\" LIKE '{p}%'")

        for f in layer.getFeatures(req):
            val = f[field_name]
            if val is None:
                continue

            s = str(val).strip()
            if not s:
                continue

            if prefix:
                if not s.startswith(prefix):
                    continue
                s = s[len(prefix):].strip()

            if s.isdigit():
                used.add(int(s))

        return used

    def update_next_number(self):
        if not hasattr(self, "next_spin"):
            return

        used = self.get_used_numbers()
        i = 1
        while i in used:
            i += 1
        self.next_spin.setValue(i)

    def apply_number(self):
        layer = self.get_target_layer()
        if not layer:
            return

        selected = layer.selectedFeatures()
        if not selected:
            self.iface.messageBar().pushWarning("Selection", "Δεν υπάρχουν επιλεγμένες γραμμές.")
            return

        idx = layer.fields().indexFromName(self.FIELD_NAME)
        if idx < 0:
            self.iface.messageBar().pushWarning("Field", f"Το πεδίο '{self.FIELD_NAME}' δεν υπάρχει στο layer.")
            return

        prefix = self.get_prefix()

        if self.cb_next.isChecked():
            number = self.next_spin.value()
            value = f"{prefix}{int(number)}"

            changed = 0
            skipped = 0

            layer.beginEditCommand("Fill od_numb (only NULL)")
            for feature in selected:
                cur = feature.attribute(idx)

                # Robust NULL/empty detection across QGIS builds
                is_empty = (
                    cur is None
                    or cur == NULL
                    or (hasattr(cur, "isNull") and cur.isNull())
                    or (isinstance(cur, str) and cur.strip() == "")
                )

                if is_empty:
                    layer.changeAttributeValue(feature.id(), idx, value)
                    changed += 1
                else:
                    skipped += 1
            layer.endEditCommand()

            if changed == 0:
                self.iface.messageBar().pushInfo("Notice", "Όλα τα επιλεγμένα είχαν ήδη τιμή — δεν άλλαξε κάτι.")
            elif skipped > 0:
                self.iface.messageBar().pushInfo(
                    "Notice",
                    f"Συμπληρώθηκαν {changed}. Παραλείφθηκαν {skipped} (είχαν ήδη τιμή)."
                )

        elif self.cb_manual.isChecked():
            number = self.manual_spin.value()
            value = f"{prefix}{int(number)}"

            layer.beginEditCommand("Set od_numb (overwrite)")
            for feature in selected:
                layer.changeAttributeValue(feature.id(), idx, value)
            layer.endEditCommand()

        else:
            self.iface.messageBar().pushWarning("Επιλογή", "Επίλεξε Επόμενη Τιμή ή Επεξεργασία Τιμής.")
            return

        self.update_next_number()

    def delete_manual_number(self):
        layer = self.get_target_layer()
        if not layer:
            return

        selected = layer.selectedFeatures()
        if not selected:
            self.iface.messageBar().pushWarning("Selection", "Δεν υπάρχουν επιλεγμένες γραμμές.")
            return

        idx = layer.fields().indexFromName(self.FIELD_NAME)

        layer.beginEditCommand("Clear od_numb")
        for feature in selected:
            layer.changeAttributeValue(feature.id(), idx, None)
        layer.endEditCommand()

        self.update_next_number()