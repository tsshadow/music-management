#include "core/Md5.hpp"

#include <iomanip>
#include <sstream>
#include <openssl/evp.h>

namespace lms::core::crypto
{
    std::string md5(std::string_view data)
    {
        EVP_MD_CTX* context = EVP_MD_CTX_new();
        const EVP_MD* md = EVP_md5();
        unsigned char md_value[EVP_MAX_MD_SIZE];
        unsigned int md_len;

        EVP_DigestInit_ex(context, md, nullptr);
        EVP_DigestUpdate(context, data.data(), data.size());
        EVP_DigestFinal_ex(context, md_value, &md_len);
        EVP_MD_CTX_free(context);

        std::stringstream ss;
        for (unsigned int i = 0; i < md_len; ++i)
            ss << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(md_value[i]);

        return ss.str();
    }
} // namespace lms::core::crypto
