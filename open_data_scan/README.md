# open_data_scan: quét doanh nghiệp từ nguồn dữ liệu mở vào Lark Base

Bộ script cho việc 1 của TGĐ: mở rộng tệp khách người Việt sang Hàn Quốc và Singapore, đổ vào bảng "Dữ liệu AI quét" trên Lark Base.

## Luồng

```
data.gov.sg (ACRA) ──► sg_acra_scan.py ──┐
                                          ├─► Lark Base "Dữ liệu AI quét"
inbox/*.csv (danh bạ công khai) ──► import_directory.py ─┘
                       run_weekly.sh (cron thứ Hai 07:59 giờ Việt Nam)
```

## Các file

| File | Việc |
|---|---|
| `sg_acra_scan.py` | Singapore: tìm doanh nghiệp đang hoạt động có từ khóa Việt Nam trong tên, bỏ trùng, ghi tối đa 60 dòng mới mỗi lần |
| `import_directory.py` | Nạp CSV danh bạ công khai (dùng cho Hàn Quốc): kiểm luật, bỏ trùng, gắn nhãn |
| `scan_common.py` | Thư viện dùng chung: Lark Open API, chống trùng, nhãn A/B/C, ngày |
| `scan_config.json` | Từ khóa, quy tắc ngành, tên cột Base. Không chứa khóa |
| `run_weekly.sh` | Chạy cả hai bước, khóa chống chạy chồng, ghi nhật ký |
| `.env.example` | Mẫu file khóa (`.env` thật quyền 600) |
| `templates/mau_danh_ba.csv` | Dòng tiêu đề cho file CSV danh bạ |
| `INSTALL_IT.md` | Hướng dẫn cài, chạy thử, đặt lịch, xử lý lỗi |

## Điều cần biết trước khi dùng

- **Vì sao không phải Google Maps:** điều khoản Google Maps Platform không cho lưu tên, địa chỉ doanh nghiệp từ Google vào cơ sở dữ liệu riêng (mục 3.2.3(a), 3.2.3(b); chỉ place_id được cache). Bộ này dùng nguồn dữ liệu mở có giấy phép cho phép lưu và dùng thương mại.
- **Dữ liệu Singapore chỉ có tên, loại hình, tình trạng, đường, mã bưu chính.** Không có điện thoại, website, ngành.
- **Nhãn A/B chỉ là gợi ý từ tên công ty**, không xác nhận chủ là người Việt.
- **Hộ kinh doanh cá thể bị loại mặc định** vì địa chỉ đăng ký có thể là nhà riêng; bật lại cần đồng ý của người phụ trách và pháp chế.
- **Hàn Quốc hiện đi qua file CSV do người chuẩn bị**, chưa tự chạy hoàn toàn.
- **Chưa chạy trực tiếp tới data.gov.sg và Lark thật trong môi trường phát triển.** Logic đã qua tự kiểm offline; lần chạy thật đầu tiên do IT làm theo `INSTALL_IT.md` mục 5.

## Tự kiểm

```bash
python3 sg_acra_scan.py --self-test
python3 import_directory.py --self-test
```
