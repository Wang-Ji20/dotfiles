// SPDX-License-Identifier: GPL-2.0
/*
 * Battery care (charge limit) for Redmi Book Pro laptops.
 *
 * The firmware exposes it through the MIFS WMI method WMAA
 * (GUID B60BFB48-3E5B-49E4-A0E9-8CFFE1B3434B), which the kernel's
 * bitland-mifs-wmi driver does not cover yet:
 *   get: WMAA(0, 1, {FA00, 1000, 0002})      -> result dword at byte 6
 *   set: WMAA(0, 1, {FB00, 1000, 0002, on})
 * Both end up in bit 0 of EC register LONL. Calling the firmware method
 * keeps the EC locking right and works under Secure Boot lockdown.
 *
 * /sys/module/redmi_battery_care/parameters/enabled  reads/writes it live.
 */
#include <linux/acpi.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/unaligned.h>

#define WMAA_PATH "\\_SB.PC00.WMID.WMAA"
#define OK        0x8000

static int wmaa(u16 fun1, u16 fun2, u16 fun3, u32 fun4, u32 *out)
{
	u8 in[32] = {};
	union acpi_object args[3] = {
		{ .integer = { ACPI_TYPE_INTEGER, 0 } },
		{ .integer = { ACPI_TYPE_INTEGER, 1 } },
		{ .buffer  = { ACPI_TYPE_BUFFER, sizeof(in), in } },
	};
	struct acpi_object_list list = { ARRAY_SIZE(args), args };
	struct acpi_buffer res = { ACPI_ALLOCATE_BUFFER, NULL };
	union acpi_object *obj;
	acpi_status st;
	int ret = 0;

	put_unaligned_le16(fun1, in + 0);
	put_unaligned_le16(fun2, in + 2);
	put_unaligned_le16(fun3, in + 4);
	put_unaligned_le32(fun4, in + 6);

	st = acpi_evaluate_object(NULL, WMAA_PATH, &list, &res);
	if (ACPI_FAILURE(st))
		return -ENODEV;

	obj = res.pointer;
	if (!obj || obj->type != ACPI_TYPE_BUFFER || obj->buffer.length < 10 ||
	    get_unaligned_le16(obj->buffer.pointer) != OK)
		ret = -EIO;
	else if (out)
		*out = get_unaligned_le32(obj->buffer.pointer + 6);

	kfree(obj);
	return ret;
}

static int care_get(u32 *on)
{
	return wmaa(0xFA00, 0x1000, 0x0002, 0, on);
}

static int care_set(bool on)
{
	return wmaa(0xFB00, 0x1000, 0x0002, on, NULL);
}

static bool initialized;

static int param_set(const char *val, const struct kernel_param *kp)
{
	bool on;
	int ret = kstrtobool(val, &on);

	if (ret)
		return ret;
	*(bool *)kp->arg = on;
	/* At modprobe time, params are parsed before init; init applies them. */
	if (!initialized)
		return 0;
	ret = care_set(on);
	if (!ret)
		pr_info("battery care %s\n", on ? "on" : "off");
	return ret;
}

static int param_get(char *buf, const struct kernel_param *kp)
{
	u32 on;
	int ret = care_get(&on);

	return ret ? ret : sysfs_emit(buf, "%u\n", on & 1);
}

static const struct kernel_param_ops care_ops = {
	.set = param_set,
	.get = param_get,
};
static bool enabled_at_load = true;
module_param_cb(enabled, &care_ops, &enabled_at_load, 0644);
MODULE_PARM_DESC(enabled, "Battery care / charge limit (1 = on)");

static int __init care_init(void)
{
	acpi_handle h;
	u32 on;
	int ret;

	if (ACPI_FAILURE(acpi_get_handle(NULL, WMAA_PATH, &h)))
		return -ENODEV;
	/* Probe the read path so unsupported firmware fails the load. */
	ret = care_get(&on);
	if (ret)
		return ret;
	if ((on & 1) != enabled_at_load) {
		ret = care_set(enabled_at_load);
		if (ret)
			return ret;
		care_get(&on);
	}
	initialized = true;
	pr_info("loaded, battery care is %s\n", (on & 1) ? "on" : "off");
	return 0;
}

static void __exit care_exit(void)
{
}

module_init(care_init);
module_exit(care_exit);
MODULE_DESCRIPTION("Redmi Book battery care (charge limit) via MIFS WMI");
MODULE_LICENSE("GPL");
