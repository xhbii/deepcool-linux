# AK620 G2 fan controls: implementation status

The Windows 1.2.14 application's AK620 G2 interface exposes these operations:

- Motherboard PWM synchronization.
- Silent AI / performance AI and sleep / office / gaming / overclocking presets.
- Manual PWM, acceleration and deceleration settings.
- RPM feedback.
- Display power and temperature alert settings.

The frontend's IPC parameters are not the device's HID packet layout. The main
implementation is stored as V8 serialized bytecode. Protocol investigation is
in progress; commands are enabled only after the report ID, field layout,
transport method and response interpretation are established.

The current released implementation sends telemetry reports only and leaves
fan configuration unchanged. Firmware updates and zero-RPM control are outside
the implemented scope.

Investigation files derived from the vendor application are kept locally and
are excluded from version control and release archives. Verified protocol
summaries and independently written implementations can be included here.
