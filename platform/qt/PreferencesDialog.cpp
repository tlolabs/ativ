// SPDX-License-Identifier: GPL-3.0-or-later
#include "PreferencesDialog.h"
#include <QDialogButtonBox>
#include <QFormLayout>
#include <QComboBox>
#include <QSpinBox>
#include <QCheckBox>
#include <QLabel>
#include <QVBoxLayout>

PreferencesDialog::PreferencesDialog(const Preferences &current, QWidget *parent)
    : QDialog(parent) {
    setWindowTitle("Preferences");
    setMinimumWidth(380);

    auto *layout = new QVBoxLayout(this);
    layout->setSpacing(16);
    layout->setContentsMargins(20, 20, 20, 16);

    auto *form = new QFormLayout;
    form->setFieldGrowthPolicy(QFormLayout::AllNonFixedFieldsGrow);
    form->setLabelAlignment(Qt::AlignLeft);

    appearanceCombo = new QComboBox;
    appearanceCombo->addItems({"System", "Light", "Dark"});
    appearanceCombo->setCurrentText(current.appearance);
    appearanceCombo->setAccessibleName("Appearance theme");
    form->addRow("Appearance", appearanceCombo);

    bitrateCombo = new QComboBox;
    bitrateCombo->addItems({"128k", "192k", "256k", "320k"});
    bitrateCombo->setCurrentText(current.bitrate);
    bitrateCombo->setAccessibleName("Default audio bitrate");
    form->addRow("Default bitrate", bitrateCombo);

    fpsSpin = new QSpinBox;
    fpsSpin->setRange(1, 240);
    fpsSpin->setValue(current.fps);
    fpsSpin->setSuffix(" fps");
    fpsSpin->setAccessibleName("Default frames per second");
    form->addRow("Default frame rate", fpsSpin);

    autoUpdateCheck = new QCheckBox("Automatically check for updates");
    autoUpdateCheck->setChecked(current.automaticUpdates);
    autoUpdateCheck->setAccessibleName("Automatically check for updates");
#if defined(Q_OS_MACOS)
    autoUpdateCheck->setEnabled(false);
    autoUpdateCheck->setToolTip("Automatic updates are disabled in internal reference builds.");
#endif
    form->addRow("", autoUpdateCheck);

    for (int i = 0; i < form->rowCount(); ++i) {
        if (auto *labelItem = form->itemAt(i, QFormLayout::LabelRole)) {
            if (auto *label = qobject_cast<QLabel *>(labelItem->widget())) {
                if (auto *fieldItem = form->itemAt(i, QFormLayout::FieldRole)) {
                    if (auto *field = fieldItem->widget()) {
                        label->setBuddy(field);
                    }
                }
            }
        }
    }

    layout->addLayout(form);

    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, this);
    connect(buttons, &QDialogButtonBox::accepted, this, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
    layout->addWidget(buttons);
}

Preferences PreferencesDialog::preferences() const {
    Preferences p;
    p.appearance = appearanceCombo->currentText();
    p.bitrate = bitrateCombo->currentText();
    p.fps = fpsSpin->value();
    p.automaticUpdates = autoUpdateCheck->isChecked();
    return p;
}
