#pragma once

#include <Wt/WResource.h>
#include "database/IDb.hpp"

namespace lms::api::muma
{
    class MumaResource : public Wt::WResource
    {
    public:
        MumaResource(db::IDb& db);
        ~MumaResource();

        void handleRequest(const Wt::Http::Request& request, Wt::Http::Response& response) override;

    private:
        db::IDb& _db;
    };
}
