# -*- encoding=utf-8 -*-
import io
import zipfile


class Zip:
    """
    zip文件压缩
    """

    @classmethod
    def compress_data(cls, files):
        """
        在内存中压缩内存的数据
        :param dict files: 待压缩的文件列表
            dict(
                '81242319_2018-10-20 02:50:06.log': b'xxxxx',
            )
        :return bytes: 压缩后结果
        """
        output_buffer = io.BytesIO()
        zip_file_buffer = zipfile.ZipFile(output_buffer, 'w', zipfile.ZIP_DEFLATED, allowZip64=False)
        for file_name, file_data in files.items():
            zip_file_buffer.writestr(file_name, file_data)
        zip_file_buffer.close()
        output_buffer.seek(0)
        ret = output_buffer.getvalue()
        output_buffer.close()
        return ret
